from fastapi.testclient import TestClient

import ai.storyteller as storyteller
import main
from main import app

client = TestClient(app)


def test_months():
    body = client.get("/api/months").json()
    assert body["latest"] == "2026-08"
    assert "2026-04" not in body["months"]


def test_dashboard_contains_facts_and_chart_data():
    body = client.get("/api/dashboard", params={"month": "2026-08"}).json()

    assert body["facts"]["headline"]["category"] == "Restaurant"
    assert "Restaurant" in body["categories"]
    assert body["monthly_spending"][-1]["month"] == "2026-08"
    assert any(row["merchant"] == "Vapiano" for row in body["merchant_breakdown"])


def test_unknown_month_is_404():
    assert client.get("/api/dashboard", params={"month": "2020-01"}).status_code == 404


def test_story_falls_back_to_templates_when_llm_is_down(monkeypatch):
    def offline(_facts):
        raise ConnectionError("ollama not running")

    monkeypatch.setattr(storyteller, "_ask_llm", offline)
    body = client.get("/api/story", params={"month": "2026-07"}).json()

    assert body["ai_available"] is False
    assert all(section["source"] == "template" for section in body["sections"].values())


def test_story_rejects_hallucinated_numbers(monkeypatch):
    monkeypatch.setattr(
        storyteller,
        "_ask_llm",
        lambda _facts: {
            "what_happened": "Your Restaurant spending increased by 250% to €149.50.",
            "why": "L'Osteria contributed the most, adding €47.50.",
            "meaning": "All of your Restaurant spending happened on weekends.",
            "next_step": "Consider setting a €50 monthly restaurant budget.",
        },
    )
    sections = storyteller.generate_story(
        client.get("/api/dashboard").json()["facts"], use_cache=False
    )["sections"]

    assert sections["what_happened"]["source"] == "template"
    assert sections["why"]["source"] == "ai"
    assert sections["meaning"]["source"] == "ai"
    assert sections["next_step"]["source"] == "ai"


def test_dashboard_has_account_and_transactions():
    body = client.get("/api/dashboard", params={"month": "2026-08"}).json()

    assert "Income" not in body["categories"]
    assert body["account"]["income"] == 2850.0
    assert body["account"]["spending"] == body["facts"]["totals"]["current"]
    assert body["transactions"][0]["amount"] == 2850.0  # salary on the 31st is newest
    assert all(t["amount"] < 0 for t in body["transactions"] if t["category"] != "Income")


def test_warm_up_prepares_stories_and_reports_progress(monkeypatch, repo):
    import warmup

    monkeypatch.setattr(storyteller, "_story_cache", {})
    monkeypatch.setattr(storyteller, "_ask_llm", lambda facts: {})  # model reachable, empty drafts
    warmup.warm_up(repo, "demo-customer")

    assert warmup.state["status"] == "ready"
    assert warmup.state["stories_ready"] == warmup.state["stories_total"] > 0
    assert client.get("/api/health").json()["warmup"]["status"] == "ready"


def test_warm_up_failure_is_reported_not_raised(monkeypatch, repo):
    import warmup

    def offline(_facts):
        raise ConnectionError("down")

    monkeypatch.setattr(storyteller, "_story_cache", {})
    monkeypatch.setattr(storyteller, "_ask_llm", offline)
    warmup.warm_up(repo, "demo-customer")
    assert warmup.state["status"] == "failed"
    assert warmup.state["error"] == "RuntimeError"  # no internal details on the public endpoint
