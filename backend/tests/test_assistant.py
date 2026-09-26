from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import ai.assistant as assistant
from ai.assistant import answer_question
from analytics.spending import load_transactions
from main import app

DATA = Path(__file__).resolve().parents[1] / "data" / "transactions.csv"


class FakeProvider:
    """Returns a scripted router reply, then a scripted answer."""

    name = "fake"
    model = "fake-model"

    def __init__(self, route=None, answer=None, fail=False):
        self.replies = [route or {}, {"answer": answer} if answer else {}]
        self.fail = fail

    def complete_json(self, prompt):
        if self.fail:
            raise ConnectionError("provider down")
        return self.replies.pop(0)


@pytest.fixture(scope="module")
def df():
    return load_transactions(DATA)


def use(monkeypatch, provider):
    monkeypatch.setattr(assistant, "get_provider", lambda: provider)


def test_advice_is_declined_without_calling_the_model(monkeypatch, df):
    use(monkeypatch, FakeProvider(fail=True))
    reply = answer_question(df, "Should I invest my savings in ETFs?", "2026-08")

    assert reply["source"] == "policy"
    assert "can't give investment" in reply["answer"]


def test_verified_ai_answer_is_kept(monkeypatch, df):
    use(monkeypatch, FakeProvider({"tool": "spending"}, "You spent €149.50 on restaurants in August 2026."))
    reply = answer_question(df, "How much did I spend on restaurants?", "2026-08")

    assert reply["tool"] == "spending"
    assert reply["plan"]["category"] == "Restaurant"
    assert reply["source"] == "ai"
    assert reply["facts"]["Total spent"] == "€149.50"


def test_hallucinated_number_falls_back_to_template(monkeypatch, df):
    use(monkeypatch, FakeProvider({"tool": "spending"}, "You spent €180.00 on restaurants."))
    reply = answer_question(df, "How much did I spend on restaurants?", "2026-08")

    assert reply["source"] == "template"
    assert reply["issues"] == ["unverified number 180"]
    assert reply["answer"].startswith("You spent €149.50 on restaurant in August 2026")


def test_everything_still_works_when_the_model_is_down(monkeypatch, df):
    use(monkeypatch, FakeProvider(fail=True))
    reply = answer_question(df, "What were my biggest payments?", "2026-08")

    assert reply["router"] == "keywords"
    assert reply["tool"] == "largest_payments"
    assert reply["source"] == "template"
    assert "€49.00 at BVG" in reply["answer"]


@pytest.mark.parametrize(
    "question, tool, category, month, compare_month",
    [
        ("Compare my groceries with last month", "compare", "Groceries", "2026-08", "2026-07"),
        ("How much did I spend on eating out in June vs May?", "compare", "Restaurant", "2026-06", "2026-05"),
        ("Where did most of my money go?", "breakdown", None, "2026-08", None),
        ("How much did I save in July?", "income", None, "2026-07", None),
        ("What do I usually spend on groceries?", "monthly_average", "Groceries", "2026-08", None),
        ("What came in and out this month?", "income", None, "2026-08", None),
    ],
)
def test_clear_phrasings_route_deterministically(monkeypatch, df, question, tool, category, month, compare_month):
    # The model suggests the wrong tool; clear keywords and months in the question win.
    use(monkeypatch, FakeProvider({"tool": "spending", "month": "2026-05"}))
    plan = answer_question(df, question, "2026-08")["plan"]

    assert (plan["tool"], plan["category"], plan["month"], plan["compare_month"]) == (
        tool, category, month, compare_month,
    )


def test_invented_merchant_or_category_is_dropped(monkeypatch, df):
    use(monkeypatch, FakeProvider({"tool": "spending", "category": "Yachts", "merchant": "Harrods"}))
    plan = answer_question(df, "How much did I spend?", "2026-08")["plan"]

    assert plan["category"] is None
    assert plan["merchant"] is None


def test_chat_endpoint(monkeypatch):
    use(monkeypatch, FakeProvider(fail=True))
    client = TestClient(app)

    body = client.post("/api/chat", json={"question": "How much did I save?", "month": "2026-08"}).json()
    assert body["tool"] == "income"
    assert "€2,424.32" in body["answer"]

    assert client.post("/api/chat", json={"question": ""}).status_code == 422
    assert client.get("/api/chat/suggestions").json()["suggestions"]


def test_follow_up_keeps_the_previous_topic(monkeypatch, df):
    use(monkeypatch, FakeProvider(fail=True))
    first = answer_question(df, "How much did I spend on restaurants?", "2026-08")
    use(monkeypatch, FakeProvider(fail=True))
    follow = answer_question(df, "And in July?", "2026-08", previous=first["plan"])

    assert follow["plan"]["tool"] == "spending"
    assert follow["plan"]["category"] == "Restaurant"
    assert follow["plan"]["month"] == "2026-07"
    assert "€50.50" in follow["answer"]


def test_answer_must_say_what_it_is_about(monkeypatch, df):
    use(monkeypatch, FakeProvider({"tool": "spending"}, "The total spent in August 2026 is €149.50."))
    reply = answer_question(df, "How much did I spend on eating out?", "2026-08")
    assert reply["source"] == "template"
    assert "missing topic (category or merchant)" in reply["issues"]

    use(monkeypatch, FakeProvider({"tool": "spending"}, "You spent €149.50 on eating out in August 2026."))
    assert answer_question(df, "How much did I spend on eating out?", "2026-08")["source"] == "ai"
