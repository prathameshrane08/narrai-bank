"""NarrAI Bank API.

Transactions -> pandas analytics -> verified facts -> LLM narration -> dashboard.
"""

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ai.assistant import SUGGESTIONS, answer_question
from ai.storyteller import generate_story, model_name
from analytics.budgets import budget_progress, budget_suggestions, without_existing_budget_advice
from analytics.feed import build_insight_feed
from analytics.insights import build_facts, comparable_months
from analytics.spending import (
    account_summary,
    merchant_breakdown,
    month_transactions,
    monthly_spending_by_category,
    spending_only,
)
import pandas as pd

import warmup
from database import make_engine, make_session_factory
from repository import CustomerRef, Repository
from tenants import Tenant, get_tenant, load_tenants

FRONTEND_ORIGINS = os.getenv("NARRAI_FRONTEND_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.getenv("NARRAI_WARMUP", "1") == "1":
        warmup.start_in_background(repository(), DEMO_CUSTOMER)
    else:
        warmup.state["status"] = "disabled"
    yield


app = FastAPI(
    lifespan=lifespan,
    title="NarrAI Bank API",
    description="AI-powered financial data storytelling. Code calculates, AI narrates.",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS.split(","),
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


def current_tenant(x_narrai_tenant: str | None = Header(None)) -> Tenant:
    """The bank this request is for, from the X-NarrAI-Tenant header (default tenant if absent)."""
    tenant = get_tenant(x_narrai_tenant)
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"Unknown tenant '{x_narrai_tenant}'.")
    return tenant


# Until authentication lands, every request acts as this demo customer of the requesting bank.
DEMO_CUSTOMER = os.getenv("NARRAI_DEMO_CUSTOMER", "demo-customer")

_repository: Repository | None = None


def repository() -> Repository:
    global _repository
    if _repository is None:
        _repository = Repository(make_session_factory(make_engine()))
    return _repository


@dataclass
class CustomerContext:
    """Everything an endpoint needs about the signed-in customer, loaded once per request."""

    tenant: Tenant
    customer: CustomerRef
    repo: Repository
    df: pd.DataFrame

    def budgets(self) -> dict[str, float]:
        return self.repo.budgets(self.customer)


def customer_context(
    tenant: Tenant = Depends(current_tenant),
    repo: Repository = Depends(repository),
) -> CustomerContext:
    customer = repo.find_customer(tenant.id, DEMO_CUSTOMER)
    if customer is None:
        raise HTTPException(
            status_code=404,
            detail=f"No customer '{DEMO_CUSTOMER}' for {tenant.bank_name}. Run `python -m seed` to load demo data.",
        )
    df = repo.transactions(customer)
    if df.empty:
        raise HTTPException(status_code=404, detail="This customer has no transactions yet.")
    return CustomerContext(tenant, customer, repo, df)


def require_feature(tenant: Tenant, feature: str) -> None:
    if not tenant.features.get(feature, False):
        raise HTTPException(status_code=403, detail=f"'{feature}' is not enabled for {tenant.bank_name}.")


def _facts_or_404(df: pd.DataFrame, month: str | None, budgets: dict[str, float] | None = None) -> dict:
    try:
        facts = build_facts(df, month)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    # Don't suggest a budget the customer already has; the story then narrates the next suggestion.
    return without_existing_budget_advice(facts, budgets or {})


@app.get("/")
def root():
    return {"status": "ok", "message": "NarrAI Bank API is running", "model": model_name()}


@app.get("/api/health")
def health():
    """Liveness plus warm-up progress (the model and recent stories are prepared at startup)."""
    return {"status": "ok", "model": model_name(), "warmup": warmup.state}


@app.get("/api/tenant")
def tenant_config(tenant: Tenant = Depends(current_tenant)):
    """Branding and feature flags for the requesting bank."""
    return tenant.model_dump()


@app.get("/api/tenants")
def tenant_list():
    """Available demo brands (for the pitch demo's brand switcher)."""
    return {"tenants": [{"id": t.id, "bank_name": t.bank_name} for t in load_tenants().values()]}


@app.get("/api/months")
def months(ctx: CustomerContext = Depends(customer_context)):
    available = comparable_months(ctx.df)
    return {"months": available, "latest": available[-1] if available else None}


@app.get("/api/dashboard")
def dashboard(
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    ctx: CustomerContext = Depends(customer_context),
):
    """Verified facts plus chart data. Fast: no LLM call."""
    df = ctx.df
    budgets = ctx.budgets()
    facts = _facts_or_404(df, month, budgets)
    spending = spending_only(df)

    monthly = monthly_spending_by_category(spending)
    monthly_spending = [
        {"month": str(period), **{category: round(float(value), 2) for category, value in row.items()}}
        for period, row in monthly.iterrows()
    ]

    return {
        "facts": facts,
        "insights": build_insight_feed(df, facts=facts, budgets=budgets),
        "account": account_summary(df, facts["month"], ctx.repo.opening_balance(ctx.customer)),
        "transactions": month_transactions(df, facts["month"]),
        "categories": list(monthly.columns),
        "monthly_spending": monthly_spending,
        "merchant_breakdown": merchant_breakdown(spending),
    }


@app.get("/api/story")
def story(
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    ctx: CustomerContext = Depends(customer_context),
):
    """The four-part narrative. Slow on first call per month (local LLM), then cached."""
    require_feature(ctx.tenant, "story")
    facts = _facts_or_404(ctx.df, month, ctx.budgets())
    return {"month": facts["month"], **generate_story(facts)}


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    month: str | None = Field(None, pattern=r"^\d{4}-\d{2}$")
    previous: dict | None = None  # the previous answer's plan, for follow-up questions


@app.get("/api/chat/suggestions")
def chat_suggestions():
    return {"suggestions": SUGGESTIONS}


@app.post("/api/chat")
def chat(request: ChatRequest, ctx: CustomerContext = Depends(customer_context)):
    """Answer a question about the customer's money from verified numbers only."""
    require_feature(ctx.tenant, "chat")
    df = ctx.df
    month = request.month or comparable_months(df)[-1]
    if month not in {str(m) for m in df["month"].unique()}:
        raise HTTPException(status_code=404, detail=f"No data for month {month}.")
    return answer_question(
        df, request.question, month, request.previous,
        advice_contact=ctx.tenant.advice_contact, budgets=ctx.budgets(),
    )


class BudgetRequest(BaseModel):
    amount: float = Field(gt=0, le=100_000)


def _budget_response(ctx: CustomerContext, month: str | None) -> dict:
    df = ctx.df
    month = month or comparable_months(df)[-1]
    budgets = ctx.budgets()
    return {
        "month": month,
        "budgets": budget_progress(df, budgets, month),
        "suggestions": budget_suggestions(df, budgets, month),
    }


@app.get("/api/budgets")
def list_budgets(
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    ctx: CustomerContext = Depends(customer_context),
):
    """Budgets with progress for a month, plus suggested budgets for categories without one."""
    return _budget_response(ctx, month)


@app.put("/api/budgets/{category}")
def set_budget(
    category: str,
    request: BudgetRequest,
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    ctx: CustomerContext = Depends(customer_context),
):
    if category not in set(spending_only(ctx.df)["category"]):
        raise HTTPException(status_code=404, detail=f"Unknown spending category '{category}'.")
    ctx.repo.set_budget(ctx.customer, category, request.amount)
    return _budget_response(ctx, month)


@app.delete("/api/budgets/{category}")
def delete_budget(
    category: str,
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    ctx: CustomerContext = Depends(customer_context),
):
    if not ctx.repo.delete_budget(ctx.customer, category):
        raise HTTPException(status_code=404, detail=f"No budget for '{category}'.")
    return _budget_response(ctx, month)
