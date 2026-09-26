from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

import ai.assistant as assistant
from analytics.budgets import budget_progress, budget_suggestions
from analytics.feed import build_insight_feed
from analytics.spending import load_transactions
from main import app

DATA = Path(__file__).resolve().parents[1] / "data" / "transactions.csv"
client = TestClient(app)
df = load_transactions(DATA)


def test_progress_status_and_history():
    progress = {b["category"]: b for b in budget_progress(df, {"Restaurant": 50, "Groceries": 150}, "2026-08")}

    restaurant = progress["Restaurant"]
    assert (restaurant["spent"], restaurant["remaining"], restaurant["status"]) == (149.5, -99.5, "over")
    assert restaurant["percent_used"] == 299.0
    assert restaurant["months_within_budget"] == 1  # May €44.70 was within; June and July €50.50 were not
    assert restaurant["months_checked"] == 3

    groceries = progress["Groceries"]
    assert (groceries["percent_used"], groceries["status"]) == (75.2, "on_track")  # €112.80 of €150
    assert list(progress) == ["Restaurant", "Groceries"]  # most urgent first


def test_close_threshold():
    item = budget_progress(df, {"Groceries": 120}, "2026-08")[0]
    assert item["percent_used"] == 94.0
    assert item["status"] == "close"


def test_month_in_progress_is_projected():
    item = budget_progress(df, {"Restaurant": 200}, "2026-08", today=date(2026, 8, 15))[0]
    assert item["in_progress"] is True
    assert item["projected"] == round(149.5 / 15 * 31, 2)
    assert item["status"] == "close"  # under budget so far, but on pace to overspend


def test_suggestions_skip_fixed_costs_and_existing_budgets():
    suggestions = {s["category"]: s["amount"] for s in budget_suggestions(df, {"Groceries": 100}, "2026-08")}
    assert suggestions["Restaurant"] == 50.0  # typical €48.57, rounded up to the next €5
    assert "Groceries" not in suggestions
    assert "Subscriptions" not in suggestions


def test_over_budget_tops_the_insight_feed():
    feed = build_insight_feed(df, budgets={"Restaurant": 50})
    assert feed[0]["type"] == "budget"
    assert feed[0]["title"] == "Over your restaurant budget"


def test_budget_api_roundtrip_is_scoped_per_bank():
    assert client.get("/api/budgets?month=2026-08").json()["budgets"] == []

    body = client.put("/api/budgets/Restaurant?month=2026-08", json={"amount": 50}).json()
    assert body["budgets"][0]["status"] == "over"
    assert all(s["category"] != "Restaurant" for s in body["suggestions"])

    # Another bank's customer does not see this budget.
    other = client.get("/api/budgets?month=2026-08", headers={"X-NarrAI-Tenant": "kestrel"}).json()
    assert other["budgets"] == []

    assert client.delete("/api/budgets/Restaurant").json()["budgets"] == []
    assert client.delete("/api/budgets/Restaurant").status_code == 404


def test_budget_validation():
    assert client.put("/api/budgets/Restaurant", json={"amount": 0}).status_code == 422
    assert client.put("/api/budgets/Income", json={"amount": 10}).status_code == 404
    assert client.put("/api/budgets/Yachts", json={"amount": 10}).status_code == 404


def test_chat_answers_budget_questions(monkeypatch):
    monkeypatch.setattr(assistant, "get_provider", lambda: (_ for _ in ()).throw(ConnectionError("offline")))
    client.put("/api/budgets/Restaurant", json={"amount": 50})

    body = client.post("/api/chat", json={"question": "Am I within my budgets?", "month": "2026-08"}).json()
    assert body["tool"] == "budget_status"
    assert "restaurant: €149.50 of €50.00, over budget" in body["answer"]


def test_existing_budget_is_not_recommended_again():
    before = client.get("/api/dashboard?month=2026-08").json()["facts"]["recommendations"]
    assert before[0]["type"] == "budget" and before[0]["category"] == "Restaurant"

    client.put("/api/budgets/Restaurant", json={"amount": 50})
    after = client.get("/api/dashboard?month=2026-08").json()["facts"]["recommendations"]
    assert all(r["type"] != "budget" for r in after)
    assert after[0]["type"] == "merchant"  # the story now narrates the next suggestion


def test_misattributed_budget_difference_is_rejected(monkeypatch):
    class Scripted:
        name, model = "fake", "fake"

        def __init__(self):
            self.replies = [
                {"tool": "budget_status"},
                {"answer": "You spent €149.50 on Restaurant, which is €50.00 over your budget of €50.00."},
            ]

        def complete_json(self, prompt):
            return self.replies.pop(0)

    scripted = Scripted()  # one instance: the router reply, then the answer reply
    monkeypatch.setattr(assistant, "get_provider", lambda: scripted)
    client.put("/api/budgets/Restaurant", json={"amount": 50})
    body = client.post("/api/chat", json={"question": "Am I within my budget?", "month": "2026-08"}).json()

    assert "wrong budget difference" in body["issues"]
    assert body["source"] == "template"
    assert body["facts"]["Restaurant over budget by"] == "€99.50"
