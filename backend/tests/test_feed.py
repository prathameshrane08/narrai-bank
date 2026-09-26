from pathlib import Path

import pandas as pd

from analytics.feed import MAX_INSIGHTS, build_insight_feed
from analytics.insights import build_facts
from analytics.spending import load_transactions, prepare_transactions
from analytics.synthetic import PERSONAS, generate_transactions

DATA = Path(__file__).resolve().parents[1] / "data" / "transactions.csv"


def test_sample_feed_is_ranked_and_capped():
    feed = build_insight_feed(load_transactions(DATA))

    assert 0 < len(feed) <= MAX_INSIGHTS
    assert [i["score"] for i in feed] == sorted((i["score"] for i in feed), reverse=True)
    assert feed[0]["type"] == "unusual_payment"  # the €36.50 Uber ride
    assert {"category_change", "savings_rate", "weekend_pattern"} <= {i["type"] for i in feed}


def test_fixed_costs_never_headline_or_appear_as_changes():
    for persona in PERSONAS:
        df = prepare_transactions(generate_transactions(persona, seed=0))
        facts = build_facts(df)
        assert "Housing" in facts["fixed_categories"]
        assert facts["headline"]["category"] not in facts["fixed_categories"]
        assert all(
            i["category"] not in facts["fixed_categories"]
            for i in build_insight_feed(df, facts=facts)
            if i["type"] == "category_change"
        )


def test_overspending_is_flagged():
    rows = [
        ("2026-06-30", "Employer", "Income", 1000.0),
        ("2026-06-10", "Shop", "Shopping", 100.0),
        ("2026-07-30", "Employer", "Income", 1000.0),
        ("2026-07-10", "Shop", "Shopping", 1500.0),
    ]
    df = prepare_transactions(pd.DataFrame(rows, columns=["date", "merchant", "category", "amount"]))
    savings = next(i for i in build_insight_feed(df) if i["type"] == "savings_rate")

    assert savings["tone"] == "warning"
    assert savings["amount"] == -500.0


def test_drop_to_zero_is_worded_as_no_spending():
    rows = [
        ("2026-06-10", "Pizzeria", "Restaurant", 80.0),
        ("2026-06-11", "Shop", "Shopping", 10.0),
        ("2026-07-11", "Shop", "Shopping", 10.0),
    ]
    df = prepare_transactions(pd.DataFrame(rows, columns=["date", "merchant", "category", "amount"]))
    titles = [i["title"] for i in build_insight_feed(df)]

    assert "No restaurant spending" in titles
