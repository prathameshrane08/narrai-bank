# NarrAI operations guide

For whoever runs NarrAI: the NarrAI team during a pilot, or the bank's platform team when it
is hosted in the bank. Covers what to watch, what the alerts mean, and what to do.

## What to run

| Component | Notes |
|---|---|
| API (`backend/`) | Stateless apart from the in-memory story cache and rate-limit counters. Run ≥2 replicas behind a load balancer in production; rate limits then need a shared store (see [Rate limiting](#rate-limiting)). |
| Database | Postgres 15+. The API runs `alembic upgrade head` on start (Docker entrypoint). Back up daily; test restores. |
| Model | Ollama with `llama3.2:3b` by default, or any OpenAI-compatible endpoint. Optional for availability: without it NarrAI serves verified template sentences. |
| Web app (`frontend/`) | The white-label app. Deployed on **Vercel** (region `fra1`, see README), or as the Docker image. Its server exchanges launch codes and holds sessions in httpOnly cookies; set `NARRAI_API_URL` and `NARRAI_WEBAPP_SECRET`. Banks that build their own app call the API directly. |

Required settings in production: `DATABASE_URL`, `NARRAI_TOKEN_SECRET` (≥32 random characters, from a
secret manager), `NARRAI_WEBAPP_SECRET` (the same value on the API and the web app), `NARRAI_FRONTEND_ORIGINS`,
`NARRAI_HTTPS=1`, `NARRAI_METRICS_TOKEN`, and `NARRAI_DEMO_MODE` left at `0`.

## Health checks

| Endpoint | Use for | Healthy when |
|---|---|---|
| `GET /api/health` | Liveness | Always `200` while the process runs; also reports startup warm-up progress |
| `GET /api/ready` | Readiness (load balancer) | `200` when the database answers. `llm` reports `ok` or `unavailable (verified templates in use)`: a missing model degrades, it doesn't take NarrAI down. `503` when the database is unreachable (details only in the server log) |

## Logs

One JSON object per line on stdout (`NARRAI_LOG_FORMAT=json`, the default). Every request produces:

```json
{"ts": "2026-09-26T20:13:21.649+00:00", "level": "info", "logger": "narrai.request", "message": "request",
 "request_id": "5b04962340574c7fa7123248d3af1860", "method": "PUT", "route": "/api/customers/{customer_ref}",
 "status": 401, "duration_ms": 7.8, "tenant": "kestrel"}
```

- **`route` is the template, never the raw path or query string**, so customer references and amounts don't
  reach log storage. Security warnings (`narrai.security`, e.g. `auth failure: invalid bank API key`) carry no
  keys or tokens.
- **`request_id`** is returned to callers as `X-Request-ID` and stored with audit events. When a bank reports a
  problem, ask for the request id and search logs and the audit trail for it. Banks may send their own id in
  `X-Request-ID` (letters, digits, `.`, `_`, `-`; up to 64 characters).

## Metrics

`GET /metrics` in Prometheus format, only when `NARRAI_METRICS_TOKEN` is set (scrapers send it as a bearer
token; otherwise the endpoint doesn't exist). Labels never contain customer data.

| Metric | Why it matters |
|---|---|
| `narrai_http_requests_total{method,route,status}`, `narrai_http_request_duration_seconds{route}` | Traffic, errors, latency |
| `narrai_llm_requests_total{purpose,outcome}`, `narrai_llm_duration_seconds{purpose}` | Model availability and speed; purpose is `story`, `chat_route` or `chat_answer` |
| `narrai_llm_tokens_total{purpose,kind}`, `narrai_llm_estimated_cost_eur_total{purpose}` | Model usage and, for hosted models, cost (set `NARRAI_LLM_PRICE_IN_PER_1K` / `_OUT_PER_1K` in EUR) |
| `narrai_narration_sentences_total{kind,section,source}` | **The trust metric**: how many sentences customers saw that the AI wrote (`ai`) vs. verified templates (`template`) |
| `narrai_guardrail_rejections_total{kind,reason}` | Why AI sentences were rejected (`unverified_number`, `wrong_direction`, `speculative_phrase`, …) |
| `narrai_statement_imports_total{tenant,format,outcome}`, `narrai_statement_entries_total{tenant,result}` | Data feed health per bank |
| `narrai_auth_failures_total{reason}`, `narrai_rate_limited_total{limit}` | Abuse and misconfiguration |

Alert rules: [`deploy/prometheus/alerts.yml`](../deploy/prometheus/alerts.yml) (a test checks they only use
metrics the API exports). Suggested dashboard rows: trust (AI share, rejection reasons), model (p50/p95 by
purpose, errors, tokens, cost), service (requests, 5xx, p95 by route), data (imports and entries per bank),
security (auth failures, rate limits).

## Runbooks

### Guardrail rejections

*Alert: over 10% of AI sentences replaced by templates for 30 minutes.* Customers still only see verified
text, so this is a quality issue, not a correctness one.

1. Check `narrai_guardrail_rejections_total` by `reason`. A single reason dominating points at the cause.
2. Did the model, prompt or model host change? Compare with the last evaluation report.
3. Run `python -m evals.run_eval --seeds 3 --months 6` and `python -m evals.run_chat_eval` against the current
   model and compare with `docs/evaluation-report.md`.
4. Roll back the model or prompt change if one happened; otherwise tighten the prompt for the dominant reason.

### Model unavailable

*Alert: over half of model calls fail for 10 minutes.* NarrAI keeps working on verified templates.

1. `GET /api/ready` → `llm` field. Check the model host (Ollama: `ollama list`; hosted: provider status).
2. Ollama unloads models when idle; `NARRAI_OLLAMA_KEEP_ALIVE` (default `30m`) keeps them warm.
3. After recovery, restart one API replica to re-run the startup warm-up, or just let stories regenerate on demand.

### Model slow

*Alert: chat model p95 above 8 seconds.* Check host CPU/GPU load and whether the model is running on CPU
(e.g. Ollama inside Docker on a Mac). A larger model needs a GPU; the 3B default answers in ~3 s on a laptop.

### Server errors

*Alert: over 2% of requests return 5xx.* Filter logs by `status >= 500` and look at the `error` field; use
`request_id` to follow one request. Check `/api/ready` (database) first.

### API slow

*Alert: p95 above 1 s outside model-backed routes.* Usually the database: check connection counts and slow
queries. Transactions are indexed by bank, account and date; very large customers (years of history) may
need pagination in a later version.

### Auth failures

*Alert: over 100 rejected credentials in 10 minutes.* Look at `reason`:
- `invalid bank API key`: a bank is using a revoked or mistyped key (check `python -m manage api-key list --bank …`),
  or someone is guessing. Guessing is rate limited (20 failures/minute per client).
- `invalid session token` / `revoked or orphaned session`: expired sessions after a secret rotation, or a customer
  who was signed out everywhere or erased.

### Rate limiting

Informational: a limit is refusing requests. If a legitimate bank hits `upload` or `session` limits during a
bulk onboarding, raise the limit in `ratelimit.py` for that period. Limits are counted per API process; with
several replicas behind a load balancer, move them to a shared store (Redis) so they apply globally. Behind a
reverse proxy set `NARRAI_TRUST_PROXY=1` so limits use the real client address.

### Import rejections

*Alert: over 20% of a bank's uploads rejected for an hour.* The bank received `422` with a message such as
"No header row with a date and an amount column". Ask the bank for a sample file (anonymised) and the
`request_id`; a new bank export layout usually needs a column alias in `importers/csv_export.py`.

## Routine operations

| Task | Command |
|---|---|
| New bank API key | `python -m manage api-key create --bank <id> --name "<purpose>"` (shown once) |
| Rotate a key | create the new key, let the bank switch, then `python -m manage api-key revoke --bank <id> --prefix <nk_…>` |
| Audit trail | `python -m manage audit --bank <id> [--customer <ref>]` or `GET /api/audit` with the bank's key |
| Retention | `python -m manage purge --bank <id> --months 24` (monthly; agree the period with the bank's DPO) |
| Rotate the web app secret | set a new `NARRAI_WEBAPP_SECRET` on the API and the web app together; existing sessions keep working, only new launches need the new value |
| Rotate the session secret | change `NARRAI_TOKEN_SECRET`; all sessions end (customers sign in again via their bank app) |
| Update the API spec | `python -m manage openapi` (CI fails if `docs/openapi.json` is out of date) |
| Re-evaluate the model | `python -m evals.run_eval …` and `python -m evals.run_chat_eval` after any model or prompt change |
