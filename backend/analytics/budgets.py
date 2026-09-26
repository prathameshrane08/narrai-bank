"""Budget progress and suggestions — all computed from transactions, never by the LLM."""

import math
from datetime import date

import pandas as pd

from analytics.insights import TRAILING_MONTHS, fixed_categories
from analytics.spending import monthly_spending_by_category, spending_only

CLOSE_THRESHOLD = 80.0  # percent of the budget used before we call it "close"
HISTORY_MONTHS = 3


def _status(percent_used: float) -> str:
    if percent_used > 100:
        return "over"
    if percent_used >= CLOSE_THRESHOLD:
        return "close"
    return "on_track"


def suggested_amount(monthly: pd.DataFrame, category: str, month: pd.Period) -> float | None:
    """Typical monthly spending before `month`, rounded up to the next €5."""
    earlier = monthly.loc[monthly.index < month, category].tail(TRAILING_MONTHS) if category in monthly else None
    if earlier is None or earlier.empty or earlier.mean() <= 0:
        return None
    return float(math.ceil(earlier.mean() / 5) * 5)


def budget_progress(df: pd.DataFrame, budgets: dict[str, float], month: str, today: date | None = None) -> list[dict]:
    spending = spending_only(df)
    monthly = monthly_spending_by_category(spending)
    period = pd.Period(month, freq="M")
    today = today or date.today()

    # For the month in progress, project month-end spending from the pace so far.
    in_progress = period == pd.Period(today, freq="M")
    days_in_month = period.days_in_month
    days_elapsed = today.day if in_progress else days_in_month

    progress = []
    for category, amount in sorted(budgets.items()):
        spent = float(monthly.at[period, category]) if period in monthly.index and category in monthly else 0.0
        percent = spent / amount * 100
        history = [
            float(monthly.at[p, category]) if p in monthly.index and category in monthly else 0.0
            for p in pd.period_range(end=period - 1, periods=HISTORY_MONTHS, freq="M")
            if p in monthly.index
        ]

        item = {
            "category": category,
            "budget": round(amount, 2),
            "spent": round(spent, 2),
            "remaining": round(amount - spent, 2),
            "percent_used": round(percent, 1),
            "status": _status(percent),
            "in_progress": in_progress,
            "projected": None,
            "months_within_budget": sum(value <= amount for value in history),
            "months_checked": len(history),
        }
        if in_progress and days_elapsed:
            projected = spent / days_elapsed * days_in_month
            item["projected"] = round(projected, 2)
            if projected > amount and item["status"] == "on_track":
                item["status"] = "close"  # on pace to overspend even if not there yet
        progress.append(item)

    # Most urgent first.
    order = {"over": 0, "close": 1, "on_track": 2}
    return sorted(progress, key=lambda b: (order[b["status"]], -b["percent_used"]))


def budget_suggestions(df: pd.DataFrame, budgets: dict[str, float], month: str) -> list[dict]:
    """Suggested budgets for variable categories that don't have one yet."""
    spending = spending_only(df)
    monthly = monthly_spending_by_category(spending)
    period = pd.Period(month, freq="M")
    fixed = set(fixed_categories(monthly, period))

    suggestions = []
    for category in monthly.columns:
        if category in budgets or category in fixed:
            continue
        amount = suggested_amount(monthly, category, period)
        if amount:
            suggestions.append({"category": category, "amount": amount})
    return sorted(suggestions, key=lambda s: -s["amount"])
