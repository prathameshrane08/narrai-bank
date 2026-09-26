"""NarrAI Bank API.

Transactions -> pandas analytics -> verified facts -> LLM narration -> dashboard.
"""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ai.assistant import SUGGESTIONS, answer_question
from ai.storyteller import generate_story, model_name
from analytics.feed import build_insight_feed
from analytics.insights import build_facts, comparable_months
from analytics.spending import (
    account_summary,
    load_transactions,
    merchant_breakdown,
    month_transactions,
    monthly_spending_by_category,
    spending_only,
)

DATA_FILE = Path(os.getenv("NARRAI_DATA_FILE", Path(__file__).parent / "data" / "transactions.csv"))
# Demo account balance before the first transaction in the data file.
OPENING_BALANCE = float(os.getenv("NARRAI_OPENING_BALANCE", "1840.00"))
FRONTEND_ORIGINS = os.getenv("NARRAI_FRONTEND_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")

app = FastAPI(
    title="NarrAI Bank API",
    description="AI-powered financial data storytelling. Code calculates, AI narrates.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS.split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _load():
    return load_transactions(DATA_FILE)


def _facts_or_404(month: str | None) -> dict:
    try:
        return build_facts(_load(), month)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/")
def health():
    return {"status": "ok", "message": "NarrAI Bank API is running", "model": model_name()}


@app.get("/api/months")
def months():
    available = comparable_months(_load())
    return {"months": available, "latest": available[-1] if available else None}


@app.get("/api/dashboard")
def dashboard(month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$")):
    """Verified facts plus chart data. Fast: no LLM call."""
    df = _load()
    facts = _facts_or_404(month)
    spending = spending_only(df)

    monthly = monthly_spending_by_category(spending)
    monthly_spending = [
        {"month": str(period), **{category: round(float(value), 2) for category, value in row.items()}}
        for period, row in monthly.iterrows()
    ]

    return {
        "facts": facts,
        "insights": build_insight_feed(df, facts=facts),
        "account": account_summary(df, facts["month"], OPENING_BALANCE),
        "transactions": month_transactions(df, facts["month"]),
        "categories": list(monthly.columns),
        "monthly_spending": monthly_spending,
        "merchant_breakdown": merchant_breakdown(spending),
    }


@app.get("/api/story")
def story(month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$")):
    """The four-part narrative. Slow on first call per month (local LLM), then cached."""
    facts = _facts_or_404(month)
    return {"month": facts["month"], **generate_story(facts)}


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    month: str | None = Field(None, pattern=r"^\d{4}-\d{2}$")
    previous: dict | None = None  # the previous answer's plan, for follow-up questions


@app.get("/api/chat/suggestions")
def chat_suggestions():
    return {"suggestions": SUGGESTIONS}


@app.post("/api/chat")
def chat(request: ChatRequest):
    """Answer a question about the customer's money from verified numbers only."""
    df = _load()
    month = request.month or comparable_months(df)[-1]
    if month not in {str(m) for m in df["month"].unique()}:
        raise HTTPException(status_code=404, detail=f"No data for month {month}.")
    return answer_question(df, request.question, month, request.previous)
