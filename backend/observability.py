"""Logs and metrics.

- Structured JSON logs (NARRAI_LOG_FORMAT=json, the default; `text` for local reading).
  Request logs carry the route template, never the raw path or query, so no customer
  references or amounts end up in log storage.
- Prometheus metrics, exposed at /metrics when NARRAI_METRICS_TOKEN is set.

Every AI call is measured by purpose (story, chat routing, chat answer): latency, outcome,
tokens and, for hosted models, an estimated cost. Guardrail outcomes are counted per
section and reason, the production version of the evaluation suite's trust metric.
"""

import json
import logging
import os
import sys
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

from prometheus_client import CollectorRegistry, Counter, Histogram

registry = CollectorRegistry(auto_describe=True)

HTTP_REQUESTS = Counter("narrai_http_requests_total", "HTTP requests", ["method", "route", "status"], registry=registry)
HTTP_LATENCY = Histogram(
    "narrai_http_request_duration_seconds", "HTTP request latency", ["route"], registry=registry,
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
LLM_REQUESTS = Counter("narrai_llm_requests_total", "Model calls", ["purpose", "outcome"], registry=registry)
LLM_LATENCY = Histogram(
    "narrai_llm_duration_seconds", "Model call latency", ["purpose"], registry=registry,
    buckets=(0.25, 0.5, 1, 2, 4, 8, 15, 30, 60, 120),
)
LLM_TOKENS = Counter("narrai_llm_tokens_total", "Model tokens", ["purpose", "kind"], registry=registry)
LLM_COST = Counter("narrai_llm_estimated_cost_eur_total", "Estimated model cost (hosted models)", ["purpose"],
                   registry=registry)
NARRATION = Counter("narrai_narration_sentences_total", "Sentences shown, by who wrote them",
                    ["kind", "section", "source"], registry=registry)
GUARDRAIL_REJECTIONS = Counter("narrai_guardrail_rejections_total", "AI sentences rejected by the guardrails",
                               ["kind", "reason"], registry=registry)
IMPORTS = Counter("narrai_statement_imports_total", "Statement uploads", ["tenant", "format", "outcome"],
                  registry=registry)
IMPORT_ENTRIES = Counter("narrai_statement_entries_total", "Statement entries by result", ["tenant", "result"],
                         registry=registry)
RATE_LIMITED = Counter("narrai_rate_limited_total", "Requests refused by rate limits", ["limit"], registry=registry)
AUTH_FAILURES = Counter("narrai_auth_failures_total", "Rejected credentials", ["reason"], registry=registry)

_llm_purpose: ContextVar[str] = ContextVar("llm_purpose", default="other")


def issue_kind(issue: str) -> str:
    """Group guardrail messages ("unverified number 180") into a small, stable label set."""
    for prefix in ("unverified number", "wrong direction", "wrong month", "wrong budget", "speculative phrase",
                   "missing topic", "missing", "too long", "not generated", "empty"):
        if issue.startswith(prefix):
            return prefix.replace(" ", "_")
    return "other"


@contextmanager
def track_llm(purpose: str):
    """Time one model call and record its outcome; providers add token counts inside it."""
    token = _llm_purpose.set(purpose)
    started = time.perf_counter()
    try:
        yield
        LLM_REQUESTS.labels(purpose, "ok").inc()
    except Exception:
        LLM_REQUESTS.labels(purpose, "error").inc()
        raise
    finally:
        LLM_LATENCY.labels(purpose).observe(time.perf_counter() - started)
        _llm_purpose.reset(token)


def record_tokens(prompt: int | None, completion: int | None) -> None:
    """Called by providers with the usage the model reported."""
    purpose = _llm_purpose.get()
    prompt, completion = prompt or 0, completion or 0
    LLM_TOKENS.labels(purpose, "prompt").inc(prompt)
    LLM_TOKENS.labels(purpose, "completion").inc(completion)
    # Local models cost nothing per token; hosted ones are priced per 1,000 tokens (EUR).
    price_in = float(os.getenv("NARRAI_LLM_PRICE_IN_PER_1K", "0"))
    price_out = float(os.getenv("NARRAI_LLM_PRICE_OUT_PER_1K", "0"))
    cost = prompt / 1000 * price_in + completion / 1000 * price_out
    if cost:
        LLM_COST.labels(purpose).inc(cost)


def record_narration(kind: str, sections: dict) -> None:
    """kind: "story" or "chat"; sections: name -> {"source", "issues"}."""
    for name, section in sections.items():
        NARRATION.labels(kind, name, section["source"]).inc()
        if section["source"] == "template":
            for issue in section.get("issues") or ["not generated"]:
                GUARDRAIL_REJECTIONS.labels(kind, issue_kind(issue)).inc()


# ------------------------------------------------------------------ logging


class JsonFormatter(logging.Formatter):
    FIELDS = ("request_id", "method", "route", "status", "duration_ms", "tenant", "event")

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in self.FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                entry[field] = value
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    if os.getenv("NARRAI_LOG_FORMAT", "json") == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(os.getenv("NARRAI_LOG_LEVEL", "INFO"))
    logging.getLogger("uvicorn.access").disabled = True  # replaced by our route-level request log
