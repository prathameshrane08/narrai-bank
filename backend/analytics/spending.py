"""Low-level aggregations over the transaction table.

Every number the product shows is computed here with pandas — never by the LLM.
"""

from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = {"date", "merchant", "category", "amount"}
# Rows in this category are money coming in; everything else is spending.
INCOME_CATEGORY = "Income"


def load_transactions(file_path: str | Path) -> pd.DataFrame:
    return prepare_transactions(pd.read_csv(file_path))


def prepare_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """Validate raw rows and add the derived columns the analytics rely on."""
    df = df.copy()
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Transactions file is missing columns: {sorted(missing)}")

    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = df["amount"].astype(float)
    df["month"] = df["date"].dt.to_period("M")
    df["is_weekend"] = df["date"].dt.dayofweek >= 5

    return df.sort_values("date").reset_index(drop=True)


def spending_only(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["category"] != INCOME_CATEGORY]


def account_summary(df: pd.DataFrame, month: str, opening_balance: float) -> dict:
    """Income, spending and end-of-month balance, from an opening balance before the first transaction."""
    period = pd.Period(month, freq="M")
    is_income = df["category"] == INCOME_CATEGORY
    signed = df["amount"].where(is_income, -df["amount"])

    in_month = df["month"] == period
    income = float(df.loc[in_month & is_income, "amount"].sum())
    spending = float(df.loc[in_month & ~is_income, "amount"].sum())

    return {
        "month": month,
        "opening_balance": round(opening_balance, 2),
        "balance": round(opening_balance + float(signed[df["month"] <= period].sum()), 2),
        "income": round(income, 2),
        "spending": round(spending, 2),
        "net": round(income - spending, 2),
    }


def month_transactions(df: pd.DataFrame, month: str) -> list[dict]:
    """The month's transactions, newest first, with income positive and spending negative."""
    rows = df[df["month"] == pd.Period(month, freq="M")].sort_values("date", ascending=False)
    return [
        {
            "date": row.date.strftime("%Y-%m-%d"),
            "merchant": row.merchant,
            "category": row.category,
            "amount": round(row.amount if row.category == INCOME_CATEGORY else -row.amount, 2),
        }
        for row in rows.itertuples(index=False)
    ]


def available_months(df: pd.DataFrame) -> list[pd.Period]:
    return sorted(df["month"].unique())


def monthly_spending_by_category(df: pd.DataFrame) -> pd.DataFrame:
    """Rows = months, columns = categories, values = total spend."""
    return (
        df.groupby(["month", "category"])["amount"]
        .sum()
        .unstack(fill_value=0.0)
        .sort_index()
    )


def merchant_spending(df: pd.DataFrame, category: str) -> pd.DataFrame:
    """Rows = months, columns = merchants within one category."""
    return (
        df[df["category"] == category]
        .groupby(["month", "merchant"])["amount"]
        .sum()
        .unstack(fill_value=0.0)
        .sort_index()
    )


def percentage_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return (current - previous) / previous * 100


def merchant_breakdown(df: pd.DataFrame) -> list[dict]:
    """Spend per (month, category, merchant) — used for drill-down charts."""
    grouped = (
        df.groupby(["month", "category", "merchant"])["amount"]
        .agg(total="sum", transactions="count")
        .reset_index()
    )

    return [
        {
            "month": str(row.month),
            "category": row.category,
            "merchant": row.merchant,
            "amount": round(float(row.total), 2),
            "transactions": int(row.transactions),
        }
        for row in grouped.itertuples(index=False)
    ]
