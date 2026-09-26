"""Turns raw transactions into a verified fact sheet.

The fact sheet answers the four NarrAI questions:
  1. What happened?      -> headline (biggest category change vs last month)
  2. Why did it happen?  -> drivers (merchants that moved the most)
  3. What does it mean?  -> patterns (weekend share, visits, average ticket, trend)
  4. What can I do next? -> recommendations + unusual-spending alerts

Everything is computed deterministically; the LLM only rephrases this output.
"""

import math

import pandas as pd

from analytics.spending import (
    available_months,
    merchant_spending,
    monthly_spending_by_category,
    percentage_change,
    spending_only,
)

# How many earlier months form the "typical" baseline.
TRAILING_MONTHS = 3
# A transaction is unusual when it is at least this many times the merchant's typical amount...
UNUSUAL_MULTIPLIER = 2.0
# ...and at least this many euros above it (ignores tiny absolute jumps).
UNUSUAL_MIN_DIFFERENCE = 10.0
# Weekend share above which we call out a weekend pattern.
WEEKEND_PATTERN_THRESHOLD = 60.0
# A category is a fixed cost when it is paid every month and varies by at most this share of its average.
FIXED_COST_TOLERANCE = 0.05
FIXED_COST_MIN_MONTHS = 3


def _money(value: float) -> float:
    return round(float(value), 2)


def _pct(value: float | None) -> float | None:
    return None if value is None else round(float(value), 1)


def comparable_months(df: pd.DataFrame) -> list[str]:
    """Months that have a previous month to compare with."""
    df = spending_only(df)
    return [str(m) for m in available_months(df)[1:]]


def _resolve_months(df: pd.DataFrame, month: str | None) -> tuple[pd.Period, pd.Period, list[pd.Period]]:
    months = available_months(df)
    if len(months) < 2:
        raise ValueError("At least two months of transactions are needed to compare spending.")

    current = months[-1] if month is None else pd.Period(month, freq="M")
    if current not in months or current == months[0]:
        raise ValueError(f"No comparable data for month {month}.")

    index = months.index(current)
    return current, months[index - 1], months[:index]


def fixed_categories(monthly: pd.DataFrame, upto: pd.Period) -> list[str]:
    """Categories like rent or subscriptions: paid every month at (almost) the same amount.

    They carry little story, so the headline and the insight feed focus on variable spending.
    """
    history = monthly.loc[:upto].tail(6)
    if len(history) < FIXED_COST_MIN_MONTHS:
        return []

    fixed = []
    for category in history.columns:
        values = history[category]
        if (values > 0).all() and values.max() - values.min() <= FIXED_COST_TOLERANCE * values.mean():
            fixed.append(category)
    return fixed


def _category_changes(monthly: pd.DataFrame, current: pd.Period, previous: pd.Period) -> list[dict]:
    changes = []
    for category in monthly.columns:
        now = monthly.at[current, category]
        before = monthly.at[previous, category]
        changes.append(
            {
                "category": category,
                "current": _money(now),
                "previous": _money(before),
                "change_amount": _money(now - before),
                "change_pct": _pct(percentage_change(now, before)),
            }
        )
    return sorted(changes, key=lambda c: abs(c["change_amount"]), reverse=True)


def _drivers(df: pd.DataFrame, category: str, current: pd.Period, previous: pd.Period) -> list[dict]:
    merchants = merchant_spending(df, category).reindex([previous, current], fill_value=0.0)
    delta = merchants.loc[current] - merchants.loc[previous]

    drivers = [
        {
            "merchant": merchant,
            "current": _money(merchants.at[current, merchant]),
            "previous": _money(merchants.at[previous, merchant]),
            "change_amount": _money(change),
        }
        for merchant, change in delta.items()
        if change != 0
    ]
    # For an increase the biggest positive movers explain it; for a decrease the biggest negative ones.
    total_change = float(delta.sum())
    return sorted(drivers, key=lambda d: d["change_amount"], reverse=total_change >= 0)


def _patterns(df: pd.DataFrame, category: str, current: pd.Period, previous: pd.Period, month_total: float) -> dict:
    now = df[(df["category"] == category) & (df["month"] == current)]
    before = df[(df["category"] == category) & (df["month"] == previous)]

    spend_now = now["amount"].sum()
    weekend_share = now.loc[now["is_weekend"], "amount"].sum() / spend_now * 100 if spend_now else 0.0

    return {
        "transactions_current": int(len(now)),
        "transactions_previous": int(len(before)),
        "average_transaction_current": _money(now["amount"].mean()) if len(now) else 0.0,
        "average_transaction_previous": _money(before["amount"].mean()) if len(before) else 0.0,
        "weekend_share_pct": _pct(weekend_share),
        "share_of_month_total_pct": _pct(spend_now / month_total * 100 if month_total else 0.0),
    }


def _unusual_transactions(df: pd.DataFrame, current: pd.Period) -> list[dict]:
    """Flag current-month transactions far above that merchant's own history."""
    alerts = []
    history = df[df["month"] < current]

    for row in df[df["month"] == current].itertuples(index=False):
        past = history.loc[history["merchant"] == row.merchant, "amount"]
        if len(past) < 2:
            continue

        typical = float(past.median())
        if row.amount >= typical * UNUSUAL_MULTIPLIER and row.amount - typical >= UNUSUAL_MIN_DIFFERENCE:
            alerts.append(
                {
                    "date": row.date.strftime("%Y-%m-%d"),
                    "merchant": row.merchant,
                    "category": row.category,
                    "amount": _money(row.amount),
                    "typical_amount": _money(typical),
                    "times_typical": round(row.amount / typical, 1),
                }
            )
    return alerts


def _recommendations(headline: dict, drivers: list[dict], patterns: dict, alerts: list[dict]) -> list[dict]:
    recs = []
    category = headline["category"]

    if headline["change_amount"] > 0:
        # Suggest a budget at the typical level, rounded up to the next €5.
        budget = math.ceil(headline["trailing_average"] / 5) * 5
        if 0 < budget < headline["current"]:
            recs.append(
                {
                    "type": "budget",
                    "title": f"Set a €{budget} monthly {category.lower()} budget",
                    "detail": (
                        f"Your typical {category.lower()} spending is €{headline['trailing_average']:.2f}. "
                        f"Staying at €{budget} would have saved €{headline['current'] - budget:.2f} this month."
                    ),
                    "amount": _money(headline["current"] - budget),
                }
            )

        if drivers and drivers[0]["change_amount"] > 0:
            top = drivers[0]
            recs.append(
                {
                    "type": "merchant",
                    "title": f"Watch your spending at {top['merchant']}",
                    "detail": (
                        f"{top['merchant']} went from €{top['previous']:.2f} to €{top['current']:.2f}. "
                        f"Returning to last month's level saves €{top['change_amount']:.2f}."
                    ),
                    "amount": top["change_amount"],
                }
            )

        if patterns["weekend_share_pct"] >= WEEKEND_PATTERN_THRESHOLD:
            recs.append(
                {
                    "type": "pattern",
                    "title": "Plan your weekends ahead",
                    "detail": (
                        f"{patterns['weekend_share_pct']:.1f}% of your {category.lower()} spending happened on weekends. "
                        f"A weekend spending limit targets where most of it happens."
                    ),
                    "amount": None,
                }
            )
    else:
        recs.append(
            {
                "type": "savings",
                "title": f"Move the €{abs(headline['change_amount']):.2f} you saved into savings",
                "detail": f"Your {category.lower()} spending fell compared with last month.",
                "amount": _money(abs(headline["change_amount"])),
            }
        )

    for alert in alerts:
        recs.append(
            {
                "type": "alert",
                "title": f"Check the €{alert['amount']:.2f} {alert['merchant']} payment",
                "detail": (
                    f"On {alert['date']} you paid €{alert['amount']:.2f} at {alert['merchant']}, "
                    f"{alert['times_typical']:.1f}x your usual €{alert['typical_amount']:.2f}."
                ),
                "amount": alert["amount"],
            }
        )

    return recs


def build_facts(df: pd.DataFrame, month: str | None = None) -> dict:
    df = spending_only(df)
    current, previous, earlier = _resolve_months(df, month)
    monthly = monthly_spending_by_category(df)

    changes = _category_changes(monthly, current, previous)
    fixed = fixed_categories(monthly, current)
    variable_changes = [c for c in changes if c["category"] not in fixed] or changes
    headline_change = variable_changes[0]
    category = headline_change["category"]

    baseline_months = earlier[-TRAILING_MONTHS:]
    trailing_average = float(monthly.loc[baseline_months, category].mean())

    headline = {
        **headline_change,
        "direction": "increase" if headline_change["change_amount"] >= 0 else "decrease",
        "trailing_average": _money(trailing_average),
        "trailing_months": len(baseline_months),
    }

    month_total = float(monthly.loc[current].sum())
    previous_total = float(monthly.loc[previous].sum())

    drivers = _drivers(df, category, current, previous)
    patterns = _patterns(df, category, current, previous, month_total)
    alerts = _unusual_transactions(df, current)

    return {
        "month": str(current),
        "month_label": current.strftime("%B %Y"),
        "previous_month": str(previous),
        "previous_month_label": previous.strftime("%B %Y"),
        "totals": {
            "current": _money(month_total),
            "previous": _money(previous_total),
            "change_amount": _money(month_total - previous_total),
            "change_pct": _pct(percentage_change(month_total, previous_total)),
        },
        "headline": headline,
        "drivers": drivers,
        "patterns": patterns,
        "alerts": alerts,
        "recommendations": _recommendations(headline, drivers, patterns, alerts),
        "category_changes": changes,
        "fixed_categories": fixed,
    }


if __name__ == "__main__":
    import json
    from pathlib import Path

    from analytics.spending import load_transactions

    data = load_transactions(Path(__file__).resolve().parents[1] / "data" / "transactions.csv")
    print(json.dumps(build_facts(data), indent=2))
