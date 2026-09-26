"""The insight feed: the handful of things worth knowing about a month.

The four-part story explains the single biggest change. The feed adds the rest:
other notable category moves, unusual payments, first-time merchants, weekend
habits and how much of the income was kept. Every card is built by code from
verified numbers and ranked by how much it matters, so the feed is safe to show
without an LLM in the loop.
"""

import pandas as pd

from analytics.budgets import budget_progress
from analytics.insights import build_facts
from analytics.spending import spending_only

MAX_INSIGHTS = 6
# A category change is notable when it moves by at least this many euros and this share.
MIN_CHANGE_EUR = 20.0
MIN_CHANGE_PCT = 20.0
# A merchant counts as new when it had no spending in this many earlier months.
NEW_MERCHANT_LOOKBACK = 3
NEW_MERCHANT_MIN_EUR = 25.0
WEEKEND_SHARE_THRESHOLD = 70.0
WEEKEND_MIN_TRANSACTIONS = 3


def _eur(value: float) -> str:
    return f"€{value:,.2f}"


def _category_moves(facts: dict) -> list[dict]:
    insights = []
    headline = facts["headline"]["category"]

    for change in facts["category_changes"]:
        category, amount, pct = change["category"], change["change_amount"], change["change_pct"]
        if category in facts["fixed_categories"] or abs(amount) < MIN_CHANGE_EUR:
            continue
        if pct is not None and abs(pct) < MIN_CHANGE_PCT:
            continue

        if pct is None:
            title = f"New spending on {category.lower()}"
            detail = f"You spent {_eur(change['current'])} on {category.lower()}, after nothing in {facts['previous_month_label']}."
            tone = "neutral"
        elif amount > 0:
            title = f"{category} up {pct:.1f}%"
            detail = (
                f"You spent {_eur(change['current'])} on {category.lower()}, "
                f"{_eur(amount)} more than in {facts['previous_month_label']}."
            )
            tone = "warning" if pct >= 50 else "neutral"
        elif change["current"] == 0:
            title = f"No {category.lower()} spending"
            detail = f"You spent nothing on {category.lower()}, after {_eur(change['previous'])} in {facts['previous_month_label']}."
            tone = "positive"
        else:
            title = f"{category} down {abs(pct):.1f}%"
            detail = (
                f"You spent {_eur(change['current'])} on {category.lower()}, "
                f"{_eur(abs(amount))} less than in {facts['previous_month_label']}."
            )
            tone = "positive"

        insights.append(
            {
                "id": f"change-{category}",
                "type": "category_change",
                "tone": tone,
                "title": title,
                "detail": detail,
                "category": category,
                "amount": change["current"],
                # Increases matter more than savings; the story's headline is already covered above.
                "score": abs(amount) * (1.0 if amount > 0 else 0.6) * (0.5 if category == headline else 1.0),
            }
        )
    return insights


def _unusual_payments(facts: dict) -> list[dict]:
    return [
        {
            "id": f"unusual-{alert['date']}-{alert['merchant']}",
            "type": "unusual_payment",
            "tone": "warning",
            "title": f"Unusual {alert['merchant']} payment",
            "detail": (
                f"On {alert['date']} you paid {_eur(alert['amount'])} at {alert['merchant']}, "
                f"{alert['times_typical']:.1f}x your usual {_eur(alert['typical_amount'])}."
            ),
            "category": alert["category"],
            "amount": alert["amount"],
            "score": 100 + alert["amount"],
        }
        for alert in facts["alerts"]
    ]


def _new_merchants(spending: pd.DataFrame, current: pd.Period, facts: dict) -> list[dict]:
    earlier = spending[(spending["month"] < current) & (spending["month"] >= current - NEW_MERCHANT_LOOKBACK)]
    if earlier["month"].nunique() < NEW_MERCHANT_LOOKBACK:
        return []  # not enough history to call anything "new"

    now = spending[spending["month"] == current]
    known = set(spending.loc[spending["month"] < current, "merchant"])
    totals = now[~now["merchant"].isin(known)].groupby(["merchant", "category"])["amount"].agg(["sum", "count"])

    insights = []
    for (merchant, category), row in totals.iterrows():
        if category in facts["fixed_categories"] or row["sum"] < NEW_MERCHANT_MIN_EUR:
            continue
        visits = int(row["count"])
        insights.append(
            {
                "id": f"new-{merchant}",
                "type": "new_merchant",
                "tone": "neutral",
                "title": f"First time at {merchant}",
                "detail": (
                    f"You spent {_eur(row['sum'])} at {merchant} ({category.lower()}) "
                    f"across {visits} {'payment' if visits == 1 else 'payments'}."
                ),
                "category": category,
                "amount": round(float(row["sum"]), 2),
                "score": 20 + float(row["sum"]) * 0.5,
            }
        )
    return insights


def _weekend_habits(spending: pd.DataFrame, current: pd.Period, facts: dict) -> list[dict]:
    now = spending[(spending["month"] == current) & ~spending["category"].isin(facts["fixed_categories"])]
    insights = []

    for category, rows in now.groupby("category"):
        if len(rows) < WEEKEND_MIN_TRANSACTIONS:
            continue
        share = rows.loc[rows["is_weekend"], "amount"].sum() / rows["amount"].sum() * 100
        if share < WEEKEND_SHARE_THRESHOLD:
            continue
        insights.append(
            {
                "id": f"weekend-{category}",
                "type": "weekend_pattern",
                "tone": "neutral",
                "title": f"{category} is a weekend habit",
                "detail": (
                    f"{share:.1f}% of your {category.lower()} spending happened on weekends "
                    f"({len(rows)} payments)."
                ),
                "category": category,
                "amount": round(float(rows["amount"].sum()), 2),
                "score": 15 + share / 10,
            }
        )
    return insights


def _income_kept(df: pd.DataFrame, current: pd.Period, facts: dict) -> list[dict]:
    month_rows = df[df["month"] == current]
    income = float(month_rows.loc[month_rows["direction"] == "in", "amount"].sum())
    if income <= 0:
        return []

    spent = float(month_rows.loc[month_rows["direction"] == "out", "amount"].sum())
    kept = income - spent
    rate = kept / income * 100

    if kept >= 0:
        title = f"You kept {rate:.1f}% of your income"
        detail = f"Money in {_eur(income)}, money out {_eur(spent)}: {_eur(kept)} left over in {facts['month_label']}."
        tone = "positive" if rate >= 10 else "neutral"
    else:
        title = "You spent more than you earned"
        detail = f"Money in {_eur(income)}, money out {_eur(spent)}: {_eur(abs(kept))} more went out than came in."
        tone = "warning"

    return [
        {
            "id": "income-kept",
            "type": "savings_rate",
            "tone": tone,
            "title": title,
            "detail": detail,
            "category": None,
            "amount": round(kept, 2),
            "score": 90 if kept < 0 else 30,
        }
    ]


def _budget_alerts(df: pd.DataFrame, facts: dict, budgets: dict[str, float]) -> list[dict]:
    insights = []
    for item in budget_progress(df, budgets, facts["month"]):
        category = item["category"]
        if item["status"] == "over":
            insights.append({
                "id": f"budget-{category}",
                "type": "budget",
                "tone": "warning",
                "title": f"Over your {category.lower()} budget",
                "detail": (
                    f"You spent {_eur(item['spent'])} of your {_eur(item['budget'])} budget, "
                    f"{_eur(abs(item['remaining']))} over."
                ),
                "category": category,
                "amount": item["spent"],
                # A goal the customer set themselves: going over it outranks every other card.
                "score": 150 + item["percent_used"] / 10,
            })
        elif item["status"] == "close":
            insights.append({
                "id": f"budget-{category}",
                "type": "budget",
                "tone": "neutral",
                "title": f"Close to your {category.lower()} budget",
                "detail": (
                    f"You used {item['percent_used']:.1f}% of your {_eur(item['budget'])} budget; "
                    f"{_eur(item['remaining'])} left."
                ),
                "category": category,
                "amount": item["spent"],
                "score": 45 + item["percent_used"] / 10,
            })
    return insights


def build_insight_feed(
    df: pd.DataFrame,
    month: str | None = None,
    facts: dict | None = None,
    budgets: dict[str, float] | None = None,
) -> list[dict]:
    """Ranked insight cards for a month; `df` may include income rows."""
    facts = facts or build_facts(df, month)
    current = pd.Period(facts["month"], freq="M")
    spending = spending_only(df)

    candidates = (
        _budget_alerts(df, facts, budgets or {})
        + _unusual_payments(facts)
        + _income_kept(df, current, facts)
        + _category_moves(facts)
        + _new_merchants(spending, current, facts)
        + _weekend_habits(spending, current, facts)
    )
    ranked = sorted(candidates, key=lambda insight: insight["score"], reverse=True)[:MAX_INSIGHTS]

    for insight in ranked:
        insight["month"] = facts["month"]
        insight["score"] = round(insight["score"], 1)
    return ranked


if __name__ == "__main__":
    import json
    from pathlib import Path

    from analytics.spending import load_transactions

    data = load_transactions(Path(__file__).resolve().parents[1] / "data" / "transactions.csv")
    print(json.dumps(build_insight_feed(data), indent=2, ensure_ascii=False))
