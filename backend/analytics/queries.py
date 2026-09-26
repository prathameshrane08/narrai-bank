"""Deterministic answers to customer questions.

The assistant never lets the LLM add up transactions. It maps a question to one
of these query functions; each computes its result with pandas and returns:

    {"tool", "args", "facts": {label: value}, "summary": str}

`facts` is what the LLM may phrase (and what the guardrails check against);
`summary` is a verified template answer used when the LLM is unavailable or
its wording fails the guardrails.
"""

import pandas as pd

from analytics.budgets import budget_progress
from analytics.insights import build_facts
from analytics.spending import INCOME_CATEGORY, percentage_change, spending_only


def _eur(value: float) -> str:
    return f"€{value:,.2f}"


def _label(month: pd.Period) -> str:
    return month.strftime("%B %Y")


def _scope(category: str | None, merchant: str | None) -> str:
    if merchant:
        return f"at {merchant}"
    if category:
        return f"on {category.lower()}"
    return "in total"


def _filter(df: pd.DataFrame, category: str | None, merchant: str | None) -> pd.DataFrame:
    rows = spending_only(df)
    if merchant:
        return rows[rows["merchant"] == merchant]
    if category:
        return rows[rows["category"] == category]
    return rows


def _what(category: str | None, merchant: str | None) -> str:
    if merchant:
        return f"Spending at {merchant}"
    if category:
        return f"{category} spending"
    return "All spending"


def _result(tool: str, args: dict, facts: dict, summary: str) -> dict:
    return {"tool": tool, "args": args, "facts": facts, "summary": summary}


def spending(df, month: pd.Period, category=None, merchant=None, **_):
    rows = _filter(df, category, merchant)
    now = rows[rows["month"] == month]
    before = rows[rows["month"] == month - 1]
    total, previous = float(now["amount"].sum()), float(before["amount"].sum())
    scope = _scope(category, merchant)

    facts = {
        "What": _what(category, merchant),
        "Month": _label(month),
        "Total spent": _eur(total),
        "Number of payments": len(now),
        "Average payment": _eur(total / len(now)) if len(now) else _eur(0),
        f"Spent in {_label(month - 1)}": _eur(previous),
    }
    summary = f"You spent {_eur(total)} {scope} in {_label(month)} across {len(now)} payments"

    change = percentage_change(total, previous)
    if change is not None and total != previous:
        facts["Change vs previous month"] = f"{'up' if total > previous else 'down'} {abs(change):.1f}%"
        summary += f", {'up' if total > previous else 'down'} {abs(change):.1f}% from {_eur(previous)} in {_label(month - 1)}"
    return _result("spending", {"month": str(month), "category": category, "merchant": merchant}, facts, summary + ".")


def top_merchants(df, month: pd.Period, category=None, n=3, **_):
    rows = _filter(df, category, None)
    now = rows[rows["month"] == month]
    top = now.groupby("merchant")["amount"].agg(["sum", "count"]).sort_values("sum", ascending=False).head(n)

    facts = {"What": _what(category, None), "Month": _label(month)}
    parts = []
    for rank, (merchant, row) in enumerate(top.iterrows(), start=1):
        facts[f"#{rank} {merchant}"] = f"{_eur(row['sum'])} ({int(row['count'])} payments)"
        parts.append(f"{merchant} ({_eur(row['sum'])})")

    scope = f"for {category.lower()} " if category else ""
    summary = (
        f"Your top merchants {scope}in {_label(month)} were " + ", ".join(parts) + "."
        if parts
        else f"You had no {category.lower() + ' ' if category else ''}spending in {_label(month)}."
    )
    return _result("top_merchants", {"month": str(month), "category": category, "n": n}, facts, summary)


def compare(df, month: pd.Period, compare_month: pd.Period, category=None, merchant=None, **_):
    rows = _filter(df, category, merchant)
    a = float(rows.loc[rows["month"] == month, "amount"].sum())
    b = float(rows.loc[rows["month"] == compare_month, "amount"].sum())
    scope = _scope(category, merchant)

    facts = {"What": _what(category, merchant), f"Spent in {_label(month)}": _eur(a), f"Spent in {_label(compare_month)}": _eur(b)}
    if a == b:
        summary = f"You spent the same {scope} in {_label(month)} and {_label(compare_month)}: {_eur(a)}."
    else:
        more = "more" if a > b else "less"
        facts["Difference"] = f"{_eur(abs(a - b))} {more} in {_label(month)}"
        change = percentage_change(a, b)
        if change is not None:
            facts["Percent difference"] = f"{abs(change):.1f}%"
        summary = (
            f"You spent {_eur(a)} {scope} in {_label(month)} and {_eur(b)} in {_label(compare_month)}, "
            f"{_eur(abs(a - b))} {more} in {_label(month)}."
        )
    args = {"month": str(month), "compare_month": str(compare_month), "category": category, "merchant": merchant}
    return _result("compare", args, facts, summary)


def largest_payments(df, month: pd.Period, category=None, n=3, **_):
    rows = _filter(df, category, None)
    top = rows[rows["month"] == month].sort_values("amount", ascending=False).head(n)

    facts = {"What": _what(category, None), "Month": _label(month)}
    parts = []
    for rank, row in enumerate(top.itertuples(index=False), start=1):
        day = row.date.strftime("%d %b")
        facts[f"#{rank}"] = f"{_eur(row.amount)} at {row.merchant} on {day}"
        parts.append(f"{_eur(row.amount)} at {row.merchant} on {day}")

    summary = (
        f"Your largest payments in {_label(month)} were " + "; ".join(parts) + "."
        if parts
        else f"You had no payments in {_label(month)}."
    )
    return _result("largest_payments", {"month": str(month), "category": category, "n": n}, facts, summary)


def breakdown(df, month: pd.Period, **_):
    now = spending_only(df)
    now = now[now["month"] == month]
    total = float(now["amount"].sum())
    by_category = now.groupby("category")["amount"].sum().sort_values(ascending=False)

    facts = {"Month": _label(month), "Total spent": _eur(total)}
    parts = []
    for category, amount in by_category.items():
        share = amount / total * 100 if total else 0.0
        facts[category] = f"{_eur(amount)} ({share:.1f}%)"
        parts.append(f"{category.lower()} {_eur(amount)} ({share:.1f}%)")

    summary = f"In {_label(month)} you spent {_eur(total)}: " + ", ".join(parts[:4]) + "."
    return _result("breakdown", {"month": str(month)}, facts, summary)


def monthly_average(df, month: pd.Period, category=None, merchant=None, months=3, **_):
    rows = _filter(df, category, merchant)
    window = pd.period_range(end=month, periods=months, freq="M")
    totals = rows.groupby("month")["amount"].sum().reindex(window, fill_value=0.0)
    average = float(totals.mean())
    scope = _scope(category, merchant)

    facts = {"What": _what(category, merchant), f"Average per month ({_label(window[0])} to {_label(window[-1])})": _eur(average)}
    for period, value in totals.items():
        facts[_label(period)] = _eur(value)
    summary = (
        f"Over the {months} months from {_label(window[0])} to {_label(window[-1])} "
        f"you spent on average {_eur(average)} per month {scope}."
    )
    args = {"month": str(month), "category": category, "merchant": merchant, "months": months}
    return _result("monthly_average", args, facts, summary)


def income(df, month: pd.Period, **_):
    rows = df[df["month"] == month]
    money_in = float(rows.loc[rows["category"] == INCOME_CATEGORY, "amount"].sum())
    money_out = float(rows.loc[rows["category"] != INCOME_CATEGORY, "amount"].sum())
    kept = money_in - money_out

    facts = {"Month": _label(month), "Money in": _eur(money_in), "Money out": _eur(money_out)}
    if money_in:
        facts["Kept"] = _eur(kept)
        facts["Share of income kept"] = f"{kept / money_in * 100:.1f}%"
        summary = (
            f"In {_label(month)} {_eur(money_in)} came in and {_eur(money_out)} went out, "
            f"so you kept {_eur(kept)} ({kept / money_in * 100:.1f}% of your income)."
        )
    else:
        summary = f"No income was booked in {_label(month)}; {_eur(money_out)} went out."
    return _result("income", {"month": str(month)}, facts, summary)


def unusual(df, month: pd.Period, **_):
    try:
        alerts = build_facts(df, str(month))["alerts"]
    except ValueError:
        alerts = []  # the first month has no history to compare against
    facts = {"Month": _label(month), "Unusual payments": len(alerts)}
    for alert in alerts:
        facts[f"{alert['merchant']} on {alert['date']}"] = (
            f"{_eur(alert['amount'])}, {alert['times_typical']:.1f}x the usual {_eur(alert['typical_amount'])}"
        )

    if alerts:
        parts = [f"{_eur(a['amount'])} at {a['merchant']} on {a['date']}" for a in alerts]
        summary = f"In {_label(month)} these payments were far above your usual: " + "; ".join(parts) + "."
    else:
        summary = f"Nothing unusual stood out in {_label(month)}."
    return _result("unusual", {"month": str(month)}, facts, summary)


def budget_status(df, month: pd.Period, category=None, budgets=None, **_):
    budgets = budgets or {}
    if category:
        budgets = {k: v for k, v in budgets.items() if k == category}
    progress = budget_progress(df, budgets, str(month))

    facts = {"Month": _label(month), "Budgets set": len(progress)}
    parts = []
    for item in progress:
        state = {"over": "over budget", "close": "close to the limit", "on_track": "within budget"}[item["status"]]
        facts[f"{item['category']} budget"] = (
            f"{_eur(item['spent'])} spent of {_eur(item['budget'])} ({item['percent_used']:.1f}%, {state})"
        )
        # State the difference explicitly so the model never has to work it out.
        if item["remaining"] < 0:
            facts[f"{item['category']} over budget by"] = _eur(abs(item["remaining"]))
        else:
            facts[f"{item['category']} left in budget"] = _eur(item["remaining"])
        parts.append(f"{item['category'].lower()}: {_eur(item['spent'])} of {_eur(item['budget'])}, {state}")

    if parts:
        summary = f"Your budgets in {_label(month)}: " + "; ".join(parts) + "."
    elif category:
        summary = f"You haven't set a {category.lower()} budget yet."
    else:
        summary = "You haven't set any budgets yet. You can add one in the Budgets section."
    return _result("budget_status", {"month": str(month), "category": category}, facts, summary)


TOOLS = {
    "spending": (spending, "How much was spent (optionally in a category or at a merchant) in a month."),
    "top_merchants": (top_merchants, "Where the most money went: top merchants in a month (optionally one category)."),
    "compare": (compare, "Compare spending between two months (optionally a category or merchant)."),
    "largest_payments": (largest_payments, "The biggest single payments in a month (optionally one category)."),
    "breakdown": (breakdown, "Spending split by category for a month."),
    "monthly_average": (monthly_average, "Average monthly spending over recent months (optionally a category or merchant)."),
    "income": (income, "Income, money out, and how much was kept or saved in a month."),
    "budget_status": (budget_status, "Whether spending is within the customer's budgets (optionally one category)."),
    "unusual": (unusual, "Payments that were unusually high compared with the merchant's history."),
}
