"""NarrAI Bank API.

Transactions -> pandas analytics -> verified facts -> LLM narration -> dashboard.
"""

import json
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from ai.assistant import SUGGESTIONS, answer_question
from ai.storyteller import clear_story_cache, generate_story, model_name
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
from auth import InvalidToken, issue_session, verify_session
from importers import MAX_BYTES, StatementError
from importers.service import import_statement
from database import make_engine, make_session_factory
from ratelimit import client_key, limiter
from repository import CustomerRef, Repository
from tenants import Tenant, get_tenant, load_tenants

logger = logging.getLogger("narrai.security")

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
    expose_headers=["X-Request-ID", "Retry-After"],
)

REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    # The API only ever returns JSON: nothing may be loaded, framed or run from its responses.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Resource-Policy": "same-site",
}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    # A request id ties logs and audit events together; accept the bank's own id if it is well-formed.
    incoming = request.headers.get("x-request-id", "")
    request.state.request_id = incoming if REQUEST_ID.match(incoming) else uuid.uuid4().hex
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    response.headers["X-Request-ID"] = request.state.request_id
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"  # financial data must never be cached
    if os.getenv("NARRAI_HTTPS", "0") == "1":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def current_tenant(x_narrai_tenant: str | None = Header(None)) -> Tenant:
    """The bank this request is for, from the X-NarrAI-Tenant header (default tenant if absent)."""
    tenant = get_tenant(x_narrai_tenant)
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"Unknown tenant '{x_narrai_tenant}'.")
    return tenant


# Demo sign-in (pick a seeded demo customer, no bank backend needed) is for pitches only: off by default.
DEMO_MODE = os.getenv("NARRAI_DEMO_MODE", "0") == "1"
# The demo customer whose recent stories are pre-written at startup.
DEMO_CUSTOMER = "demo-customer"

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


bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def _auth_failed(request: Request, reason: str) -> None:
    """Count failed authentication per client (brute-force protection) and log it without secrets."""
    logger.warning("auth failure: %s (client=%s, request=%s)", reason, client_key(request), request.state.request_id)
    limiter.check("auth_failure", client_key(request))


def signed_in_customer(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    x_narrai_tenant: str | None = Header(None),
    repo: Repository = Depends(repository),
) -> tuple[Tenant, CustomerRef]:
    """The bank and customer named in the session token. The bank never comes from a header."""
    if credentials is None:
        raise _unauthorized("Sign in required.")
    try:
        claims = verify_session(credentials.credentials)
    except InvalidToken:
        _auth_failed(request, "invalid session token")
        raise _unauthorized("Your session is invalid or has expired. Please sign in again.") from None

    tenant = get_tenant(claims["tenant"])
    customer = repo.customer_by_id(claims["tenant"], claims["sub"]) if tenant else None
    signed_out = customer is not None and (
        claims.get("gen", 0) != customer.session_generation or repo.is_session_revoked(claims["jti"])
    )
    if tenant is None or customer is None or signed_out:
        _auth_failed(request, "revoked or orphaned session")
        raise _unauthorized("Your session is no longer valid. Please sign in again.")
    if x_narrai_tenant and x_narrai_tenant != tenant.id:
        raise HTTPException(status_code=403, detail="This session belongs to a different bank.")
    request.state.session_claims = claims
    return tenant, customer


def customer_context(
    signed_in: tuple[Tenant, CustomerRef] = Depends(signed_in_customer),
    repo: Repository = Depends(repository),
) -> CustomerContext:
    tenant, customer = signed_in
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
    """Available demo brands for the pitch demo's brand switcher. Hidden outside demo mode:
    which banks use NarrAI is confidential."""
    if not DEMO_MODE:
        return {"tenants": []}
    return {"tenants": [{"id": t.id, "bank_name": t.bank_name} for t in load_tenants().values()]}


# ------------------------------------------------------------------ sessions


class SessionRequest(BaseModel):
    customer_ref: str = Field(min_length=1, max_length=80, description="The bank's own id for the customer")


def _session_response(customer: CustomerRef) -> dict:
    token, expires = issue_session(customer.tenant_id, customer.id, customer.session_generation)
    return {
        "token": token,
        "token_type": "Bearer",
        "expires_at": expires.isoformat(),
        "customer": {"ref": customer.external_ref, "name": customer.display_name},
    }


@dataclass(frozen=True)
class BankCaller:
    tenant_id: str
    key_prefix: str  # identifies which key was used, for the audit log


def bank_from_api_key(
    request: Request,
    x_narrai_api_key: str | None = Header(None),
    repo: Repository = Depends(repository),
) -> BankCaller:
    """Server-to-server calls: the bank is identified by its API key."""
    found = repo.tenant_for_api_key(x_narrai_api_key) if x_narrai_api_key else None
    if found is None:
        _auth_failed(request, "invalid bank API key")
        raise HTTPException(status_code=401, detail="A valid bank API key is required (X-NarrAI-API-Key).")
    return BankCaller(*found)


def audit(request: Request, repo: Repository, tenant_id: str, actor: tuple[str, str], action: str,
          customer: CustomerRef | None = None, **details) -> None:
    repo.audit(tenant_id, actor[0], actor[1], action, customer.id if customer else None,
               request.state.request_id, details or None)


@app.post("/api/sessions")
def create_session(
    body: SessionRequest,
    request: Request,
    bank: BankCaller = Depends(bank_from_api_key),
    repo: Repository = Depends(repository),
):
    """Server-to-server: the bank's backend, after signing its customer in, gets a NarrAI session for them."""
    limiter.check("session", bank.key_prefix)
    customer = repo.find_customer(bank.tenant_id, body.customer_ref)
    if customer is None:
        raise HTTPException(status_code=404, detail="No such customer at this bank.")
    audit(request, repo, bank.tenant_id, ("bank", bank.key_prefix), "session.created", customer)
    return _session_response(customer)


class DemoSessionRequest(BaseModel):
    customer_ref: str = Field(pattern=r"^demo-[a-z0-9-]{1,60}$")


@app.get("/api/demo/customers")
def demo_customers(tenant: Tenant = Depends(current_tenant), repo: Repository = Depends(repository)):
    """Demo customers to choose from on the demo sign-in screen (demo mode only)."""
    if not DEMO_MODE:
        raise HTTPException(status_code=404, detail="Not found.")
    return {"customers": [{"ref": c.external_ref, "name": c.display_name} for c in repo.demo_customers(tenant.id)]}


@app.post("/api/demo/sessions")
def create_demo_session(
    body: DemoSessionRequest,
    request: Request,
    tenant: Tenant = Depends(current_tenant),
    repo: Repository = Depends(repository),
):
    """Demo sign-in without a bank backend. Only in demo mode, and only for seeded demo customers."""
    if not DEMO_MODE:
        raise HTTPException(status_code=404, detail="Not found.")
    limiter.check("session", client_key(request))
    customer = repo.find_customer(tenant.id, body.customer_ref)
    if customer is None:
        raise HTTPException(status_code=404, detail="No such demo customer.")
    audit(request, repo, tenant.id, ("customer", customer.id), "session.created", customer, via="demo")
    return _session_response(customer)


@app.post("/api/sessions/current/revoke", status_code=204)
def sign_out(request: Request, signed_in: tuple[Tenant, CustomerRef] = Depends(signed_in_customer),
             repo: Repository = Depends(repository)):
    """Sign out: this session token stops working immediately, not just when it expires."""
    tenant, customer = signed_in
    claims = request.state.session_claims
    repo.revoke_session(claims["jti"], datetime.fromtimestamp(claims["exp"], tz=timezone.utc))
    audit(request, repo, tenant.id, ("customer", customer.id), "session.revoked", customer)
    return Response(status_code=204)


def _all_months(df: pd.DataFrame) -> list[str]:
    return sorted({str(m) for m in df["month"].unique()})


@app.get("/api/months")
def months(ctx: CustomerContext = Depends(customer_context)):
    """Every month with data, and which of them have a previous month to compare with (story, insights)."""
    available = _all_months(ctx.df)
    return {"months": available, "comparable": comparable_months(ctx.df), "latest": available[-1]}


@app.get("/api/dashboard")
def dashboard(
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    ctx: CustomerContext = Depends(customer_context),
):
    """Verified facts plus chart data. Fast: no LLM call.

    A month without a previous month (e.g. a newly imported customer) still gets its balance,
    transactions and charts; `facts` is null because there is nothing to compare yet."""
    df = ctx.df
    budgets = ctx.budgets()
    month = month or _all_months(df)[-1]
    if month not in _all_months(df):
        raise HTTPException(status_code=404, detail=f"No data for month {month}.")
    facts = _facts_or_404(df, month, budgets) if month in comparable_months(df) else None
    spending = spending_only(df)

    monthly = monthly_spending_by_category(spending)
    monthly_spending = [
        {"month": str(period), **{category: round(float(value), 2) for category, value in row.items()}}
        for period, row in monthly.iterrows()
    ]

    return {
        "month": month,
        "facts": facts,
        "notice": None if facts else "Stories and comparisons start once there is a previous month to compare with.",
        "insights": build_insight_feed(df, facts=facts, budgets=budgets) if facts else [],
        "account": account_summary(df, month, ctx.repo.opening_balance(ctx.customer)),
        "transactions": month_transactions(df, month),
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
    limiter.check("chat", ctx.customer.id)  # each question costs model time
    df = ctx.df
    month = request.month or _all_months(df)[-1]
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
    month = month or _all_months(df)[-1]
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
    body: BudgetRequest,
    request: Request,
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    ctx: CustomerContext = Depends(customer_context),
):
    if category not in set(spending_only(ctx.df)["category"]):
        raise HTTPException(status_code=404, detail=f"Unknown spending category '{category}'.")
    ctx.repo.set_budget(ctx.customer, category, body.amount)
    audit(request, ctx.repo, ctx.tenant.id, ("customer", ctx.customer.id), "budget.set", ctx.customer,
          category=category)
    return _budget_response(ctx, month)


@app.delete("/api/budgets/{category}")
def delete_budget(
    category: str,
    request: Request,
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    ctx: CustomerContext = Depends(customer_context),
):
    if not ctx.repo.delete_budget(ctx.customer, category):
        raise HTTPException(status_code=404, detail=f"No budget for '{category}'.")
    audit(request, ctx.repo, ctx.tenant.id, ("customer", ctx.customer.id), "budget.deleted", ctx.customer,
          category=category)
    return _budget_response(ctx, month)


# ------------------------------------------------------------------ bank data feeds (API key)

CUSTOMER_REF = Path(pattern=r"^[A-Za-z0-9._:-]{1,80}$", description="The bank's own id for the customer")


class CustomerProvision(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)


@app.put("/api/customers/{customer_ref}")
def provision_customer(
    body: CustomerProvision,
    request: Request,
    customer_ref: str = CUSTOMER_REF,
    bank: BankCaller = Depends(bank_from_api_key),
    repo: Repository = Depends(repository),
):
    """Create a customer if it doesn't exist yet (idempotent)."""
    customer, created = repo.ensure_customer(bank.tenant_id, customer_ref, body.display_name)
    if created:
        audit(request, repo, bank.tenant_id, ("bank", bank.key_prefix), "customer.provisioned", customer)
    return {"ref": customer.external_ref, "created": created}


@app.post("/api/customers/{customer_ref}/statements")
async def upload_statement(
    request: Request,
    customer_ref: str = CUSTOMER_REF,
    bank: BankCaller = Depends(bank_from_api_key),
    repo: Repository = Depends(repository),
):
    """Import a camt.053, MT940 or CSV statement (raw request body) for one customer.
    Re-sending a statement is safe: already-imported entries are recognised and skipped."""
    limiter.check("upload", bank.tenant_id)
    declared = int(request.headers.get("content-length") or 0)
    if declared > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Statement file is too large.")
    data = await request.body()
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Statement file is too large.")

    customer = repo.find_customer(bank.tenant_id, customer_ref)
    if customer is None:
        raise HTTPException(status_code=404, detail="Unknown customer; provision it first (PUT /api/customers/{ref}).")
    try:
        summary = await run_in_threadpool(import_statement, repo, customer, data)
    except StatementError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    audit(request, repo, bank.tenant_id, ("bank", bank.key_prefix), "statement.imported", customer,
          format=summary["format"], imported=summary["imported"], duplicates=summary["duplicates"])
    return summary


def _bank_customer(bank: BankCaller, customer_ref: str, repo: Repository) -> CustomerRef:
    customer = repo.find_customer(bank.tenant_id, customer_ref)
    if customer is None:
        raise HTTPException(status_code=404, detail="No such customer at this bank.")
    return customer


@app.post("/api/customers/{customer_ref}/sessions/revoke-all", status_code=204)
def sign_out_everywhere(request: Request, customer_ref: str = CUSTOMER_REF,
                        bank: BankCaller = Depends(bank_from_api_key), repo: Repository = Depends(repository)):
    """Bank-initiated: end every session of this customer (lost phone, suspected fraud, closed account)."""
    customer = _bank_customer(bank, customer_ref, repo)
    repo.revoke_all_sessions(customer)
    audit(request, repo, bank.tenant_id, ("bank", bank.key_prefix), "sessions.revoked_all", customer)
    return Response(status_code=204)


# ------------------------------------------------------------------ GDPR


@app.get("/api/me/export")
def export_my_data(request: Request, signed_in: tuple[Tenant, CustomerRef] = Depends(signed_in_customer),
                   repo: Repository = Depends(repository)):
    """The signed-in customer's own data, as a portable JSON download (GDPR Art. 15 and 20)."""
    tenant, customer = signed_in
    limiter.check("export", customer.id)
    audit(request, repo, tenant.id, ("customer", customer.id), "data.exported", customer)
    return Response(
        content=_json(repo.export_customer(customer)),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="my-data.json"'},
    )


@app.get("/api/customers/{customer_ref}/export")
def export_customer_data(request: Request, customer_ref: str = CUSTOMER_REF,
                         bank: BankCaller = Depends(bank_from_api_key), repo: Repository = Depends(repository)):
    """The bank answers a customer's access request with everything NarrAI stores about them."""
    customer = _bank_customer(bank, customer_ref, repo)
    limiter.check("export", bank.tenant_id)
    audit(request, repo, bank.tenant_id, ("bank", bank.key_prefix), "data.exported", customer)
    return repo.export_customer(customer)


@app.delete("/api/customers/{customer_ref}")
def delete_customer(request: Request, customer_ref: str = CUSTOMER_REF,
                    bank: BankCaller = Depends(bank_from_api_key), repo: Repository = Depends(repository)):
    """Erase a customer and all their data (GDPR Art. 17). Their sessions stop working at once."""
    customer = _bank_customer(bank, customer_ref, repo)
    removed = repo.delete_customer(customer)
    clear_story_cache()  # cached stories may contain the customer's figures
    audit(request, repo, bank.tenant_id, ("bank", bank.key_prefix), "customer.deleted", customer, **removed)
    return {"deleted": True, "removed": removed}


@app.get("/api/audit")
def audit_log(customer_ref: str | None = Query(None, pattern=r"^[A-Za-z0-9._:-]{1,80}$"),
              bank: BankCaller = Depends(bank_from_api_key), repo: Repository = Depends(repository)):
    """The bank's own audit trail (optionally for one customer). Contains no personal data."""
    customer_id = None
    if customer_ref:
        customer = repo.find_customer(bank.tenant_id, customer_ref)
        customer_id = customer.id if customer else "none"
    return {"events": repo.audit_events(bank.tenant_id, customer_id, limit=500)}


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)
