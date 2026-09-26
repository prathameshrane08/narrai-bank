from pathlib import Path

import pytest

from analytics.insights import build_facts, comparable_months
from analytics.spending import load_transactions

DATA = Path(__file__).resolve().parents[1] / "data" / "transactions.csv"


@pytest.fixture(scope="module")
def df():
    return load_transactions(DATA)


def test_latest_month_headline_is_restaurant(df):
    facts = build_facts(df)

    assert facts["month"] == "2026-08"
    assert facts["headline"]["category"] == "Restaurant"
    assert facts["headline"]["current"] == 149.5
    assert facts["headline"]["previous"] == 50.5
    assert facts["headline"]["change_pct"] == 196.0


def test_biggest_driver_is_losteria(df):
    top = build_facts(df)["drivers"][0]

    assert top["merchant"] == "L'Osteria"
    assert top["change_amount"] == 47.5


def test_all_restaurant_spending_was_on_weekends(df):
    assert build_facts(df)["patterns"]["weekend_share_pct"] == 100.0


def test_unusual_uber_ride_is_flagged(df):
    alerts = build_facts(df)["alerts"]

    assert [a["merchant"] for a in alerts] == ["Uber"]
    assert alerts[0]["amount"] == 36.5


def test_recommendations_start_with_budget(df):
    recs = build_facts(df)["recommendations"]

    assert recs[0]["type"] == "budget"
    assert recs[0]["amount"] == 99.5


def test_can_analyse_earlier_month(df):
    facts = build_facts(df, "2026-06")
    assert facts["previous_month"] == "2026-05"


def test_first_month_has_nothing_to_compare(df):
    assert "2026-04" not in comparable_months(df)
    with pytest.raises(ValueError):
        build_facts(df, "2026-04")
