# NarrAI Bank

An AI-powered banking dashboard that turns transactions into a short, verified story:

1. **What happened?** — "Your restaurant spending increased by 196.0%, reaching €149.50."
2. **Why did it happen?** — "L'Osteria contributed the most, adding €47.50."
3. **What does it mean?** — "100.0% of your restaurant spending happened on weekends."
4. **What can I do next?** — budgets, merchant savings, weekend patterns, unusual-payment alerts.

| Story with verified AI sentences | Chat answer with its calculation |
|---|---|
| ![Overview](docs/screenshots/01-overview.jpg) | ![Chat](docs/screenshots/05-chat-verified-answer.jpg) |
| **Insight feed** | **Budgets** |
| ![Insight feed](docs/screenshots/02-insight-feed.jpg) | ![Budgets](docs/screenshots/04-budgets.jpg) |
| **White-label: Kestrel Bank (fictional)** | **White-label: Aurelia Privatbank (fictional)** |
| ![Kestrel](docs/screenshots/06-white-label-kestrel.jpg) | ![Aurelia](docs/screenshots/07-white-label-aurelia.jpg) |

**For a pitch:** [demo script](docs/demo-script.md) · [evaluation report](docs/evaluation-report.md) ·
[all screenshots](docs/screenshots/)
**For banks and operators:** [integration guide](docs/integration-guide.md) · [API spec](docs/openapi.json) ·
[operations guide](docs/operations.md) · [alert rules](deploy/prometheus/alerts.yml)

## Code calculates. AI narrates.

```
transactions.csv → pandas analytics → verified facts → Llama 3.2 (Ollama) → guardrails → FastAPI → Next.js
```

- `backend/analytics/` computes every number: category changes, merchant drivers, patterns,
  recommendations and unusual transactions. The headline category is picked automatically
  (largest € change vs last month).
- `backend/ai/storyteller.py` gives the LLM a pre-formatted fact sheet and asks for one sentence per question.
- `backend/ai/guardrails.py` rejects any sentence with a number that is not in the facts, speculative
  language, or a missing key entity. Rejected sentences, and every sentence when Ollama is offline,
  fall back to deterministic templates. The UI badges each sentence as **AI · verified** or **From facts**.

## Run it with Docker (one command)

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine with Compose v2.24+).

```bash
docker compose up --build
```

Then open http://localhost:3000. The first start downloads the Llama 3.2 3B model (~2 GB) into a Docker
volume; later starts reuse it. Budgets are kept in the `narrai-data` volume.

- **Mac:** Ollama inside Docker runs on the CPU only. For GPU speed, install the native
  [Ollama app](https://ollama.com), run `ollama pull llama3.2:3b`, and start only the app containers:
  `docker compose -f docker-compose.yml -f docker-compose.host-ollama.yml up --build backend frontend`
- **Another bank's branding:** `NARRAI_TENANT=kestrel docker compose up --build`
- **Another model:** `NARRAI_MODEL=llama3.1:8b docker compose up --build`

## Deploying the web app on Vercel

The Next.js app (`frontend/`) deploys to Vercel as is; its server parts (`/launch`, `/bff/*`, `proxy.ts`) run
as stateless functions. The Python API, Postgres and the model run elsewhere (Vercel can't host the model).

1. Import the repository in Vercel with **Root Directory `frontend`** (Next.js is detected automatically).
2. `frontend/vercel.json` pins functions to **Frankfurt (`fra1`)** so customer sessions are handled in the EU.
3. Set environment variables (Production and Preview):

   | Variable | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | Public HTTPS URL of the NarrAI API |
   | `NARRAI_API_URL` | Same, or a private URL the functions can reach |
   | `NARRAI_WEBAPP_SECRET` | The same random secret the API has |
   | `NEXT_PUBLIC_TENANT` | The bank's tenant id (one Vercel project per bank, or a custom domain per bank) |
   | `NEXT_PUBLIC_CONTACT_EMAIL` | Optional: shows a "Talk to us about a pilot" link on the landing page |

4. On the API: add the Vercel domain (and the bank's custom domain) to `NARRAI_FRONTEND_ORIGINS`, set the bank's
   `app_url` in its tenant config to that domain, and keep `NARRAI_DEMO_MODE=0` for real customers.
5. Add the bank's custom domain in Vercel (e.g. `insights.bank.de`) so the session cookie is first-party.

## Continuous integration

`.github/workflows/ci.yml` runs on every push to `main` and every pull request:
backend tests (Python 3.13), frontend lint + type check + production build (Node 24), and a build of
both Docker images. Dependabot (`.github/dependabot.yml`) opens weekly update PRs for Python, npm,
Docker base images and GitHub Actions. LLM evaluations are not part of CI because they need a model;
run them locally (see below).

## Run it without Docker

Prerequisites: Python 3.11+, Node 20+, [Ollama](https://ollama.com) with `ollama pull llama3.2:3b`.

```bash
# backend (from the repo root)
python -m venv venv && source venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend
alembic upgrade head      # create/upgrade the database (SQLite file by default)
python -m seed            # demo customers for every bank (safe to re-run)
export NARRAI_WEBAPP_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
NARRAI_DEMO_MODE=1 uvicorn main:app --reload --port 8000   # demo sign-in on

# frontend: give the web app's server the same secret (frontend/.env.local is git-ignored)
printf 'NARRAI_API_URL=http://127.0.0.1:8000\nNARRAI_WEBAPP_SECRET=%s\n' "$NARRAI_WEBAPP_SECRET" > ../frontend/.env.local

# frontend (second terminal)
cd frontend && npm install && npm run dev
```

Open http://localhost:3000: the landing page for banks is at `/`, the product at `/app`. The first story for a
month takes a few seconds (local LLM); it is cached afterwards.

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///backend/data/narrai-dev.db` | Postgres in production, e.g. `postgresql+psycopg://user:pass@host/narrai` |
| `NARRAI_TOKEN_SECRET` | dev file `backend/data/.token-secret` | **Required in production**: ≥32 random characters used to sign session tokens |
| `NARRAI_SESSION_MINUTES` | `30` | Session token lifetime |
| `NARRAI_LOG_FORMAT` / `NARRAI_LOG_LEVEL` | `json` / `INFO` | Structured JSON logs (`text` for local reading) |
| `NARRAI_METRICS_TOKEN` | – | Enables `GET /metrics` (Prometheus) for scrapers presenting this bearer token |
| `NARRAI_LLM_PRICE_IN_PER_1K` / `_OUT_PER_1K` | `0` | EUR per 1,000 tokens, for the hosted-model cost metric |
| `NARRAI_RATE_LIMITS` | `1` | `0` disables rate limiting (e.g. load tests) |
| `NARRAI_TRUST_PROXY` | `0` | `1` only behind a trusted reverse proxy: rate-limit by `X-Forwarded-For` |
| `NARRAI_HTTPS` | `0` | `1` adds `Strict-Transport-Security` (set when served over https) |
| `NARRAI_DEMO_MODE` | `0` | `1` enables the demo sign-in screen (seeded `demo-*` customers only) and the demo brand list |
| `NARRAI_SEED_DEMO` | `0` | Docker only: `1` loads demo customers on start (Compose sets it) |
| `NARRAI_LLM_PROVIDER` | `ollama` | `ollama` (local, data stays on the machine) or `openai_compatible` (vLLM, EU-hosted APIs, Azure OpenAI…) |
| `NARRAI_MODEL` | `llama3.2:3b` | Model name for the chosen provider |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama server |
| `NARRAI_LLM_BASE_URL` / `NARRAI_LLM_API_KEY` | – | Endpoint and key for `openai_compatible` |
| `NARRAI_LLM_TIMEOUT` | `120` | Seconds before falling back to templates |
| `NARRAI_OLLAMA_KEEP_ALIVE` | `30m` | How long Ollama keeps the model loaded between requests (avoids ~60s cold starts) |
| `NARRAI_WARMUP` | `1` | Load the model and pre-write each bank's latest stories at startup (`0` to disable) |
| `NARRAI_FRONTEND_ORIGINS` | `http://localhost:3000,...` | CORS origins |
| `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8000` | API URL the browser uses for public calls (branding) |
| `NARRAI_API_URL` (web app server) | `NEXT_PUBLIC_API_URL` | API URL the web app's server uses for customer data |
| `NARRAI_WEBAPP_SECRET` (API **and** web app server) | – | Shared secret for launch-code exchange (≥32 random characters); required for the web app's sign-in |

## API

| Endpoint | Returns |
|---|---|
| `GET /api/health` | Liveness and startup warm-up progress (`idle`, `running`, `ready`, `failed`) |
| `GET /api/ready` | Readiness: `503` if the database is down; reports whether the model is available |
| `GET /api/months` | Months that have a previous month to compare with |
| `GET /api/dashboard?month=YYYY-MM` | Verified facts, account summary, transactions and chart data (fast, no LLM) |
| `GET /api/story?month=YYYY-MM` | Four-part narrative with per-sentence source |
| `POST /api/launch-codes` | **Bank backend**: one-time link that opens the white-label web app for a signed-in customer |
| `POST /api/launch-codes/exchange` | **Web app server only** (`X-NarrAI-Client-Secret`): swap a launch code for a session |
| `POST /api/sessions` | **Bank backend** (`X-NarrAI-API-Key`) gets a session token for one of its customers |
| `POST /api/sessions/current/revoke` | Customer signs out: the token stops working immediately |
| `POST /api/customers/{ref}/sessions/revoke-all` | **Bank**: sign a customer out everywhere |
| `GET /api/me/export` | Customer downloads everything stored about them (JSON) |
| `GET /api/customers/{ref}/export`, `DELETE /api/customers/{ref}` | **Bank**: GDPR access and erasure requests |
| `GET /api/audit?customer_ref=` | **Bank**: its audit trail (no personal data) |
| `GET /api/demo/customers`, `POST /api/demo/sessions` | Demo sign-in (only when `NARRAI_DEMO_MODE=1`, only `demo-*` customers) |
| `POST /api/chat` | Answer a customer question from verified numbers |
| `GET /api/chat/suggestions` | Example questions for the chat UI |

## White-label (one config per bank)

Each bank is a JSON file in `backend/tenants/` (examples: `narrai`, `kestrel`, `aurelia` — the latter two
are fictional demo brands) with its name, assistant name, logo (`frontend/public/tenants/`), colours,
account label, legal footer, where regulated-advice questions are referred, and feature flags
(`story`, `chat`, `insights`).

- The tenant is chosen per request with the `X-NarrAI-Tenant` header; the frontend sets it from
  `NEXT_PUBLIC_TENANT` or, for demos, `?bank=<id>` (the footer has a brand switcher).
- Configs are validated on load: colours must meet **WCAG AA contrast (4.5:1)**, logos must be local
  files, and the file name must match the id — a bank cannot ship an unreadable theme.
- `GET /api/tenant` returns the requesting bank's config; disabled features return `403`.

## Sign-in and bank API keys

NarrAI never handles customer passwords. The bank signs its customer in, then the bank's **backend**
asks NarrAI for a short-lived session for that customer:

```
bank backend ──X-NarrAI-API-Key──► POST /api/sessions {"customer_ref": "<bank's customer id>"}
                                  ◄── {"token": "...", "expires_at": "..."}   (30 minutes)
customer app ──Authorization: Bearer <token>──► /api/dashboard, /api/chat, /api/budgets, …
```

- **The bank comes from the session token**, never from a header a browser could change; a mismatching
  `X-NarrAI-Tenant` header is refused (403). Tokens are HS256-signed, expire, and are checked for
  issuer, algorithm and required claims.
- **API keys** are per bank, shown once, stored only as a SHA-256 hash, identified by prefix:
  ```bash
  python -m manage api-key create --bank kestrel --name "Kestrel mobile backend"
  python -m manage api-key list   --bank kestrel
  python -m manage api-key revoke --bank kestrel --prefix nk_AbCdEfGh
  ```
- **Demo sign-in** (`NARRAI_DEMO_MODE=1`) lets a pitch pick a seeded demo customer without a bank
  backend. It is off by default, only works for `demo-*` customers, and the list of client banks is only
  public in demo mode.
- **The white-label web app never exposes the session to page scripts.** Banks open it with a one-time
  launch code (`POST /api/launch-codes` → `launch_url`, valid 60 s, single use); the web app's server exchanges
  it using `NARRAI_WEBAPP_SECRET`, keeps the session in an httpOnly cookie and forwards only customer endpoints
  (`frontend/app/bff/`). The demo sign-in uses the same cookie. See the integration guide §5a.

## Importing bank statements

Banks send statements server-to-server with their API key; the format is detected automatically.

```bash
# provision a customer (idempotent), then upload a camt.053 / MT940 / CSV file as the request body
curl -X PUT  $API/api/customers/c-1042 -H "X-NarrAI-API-Key: $KEY" -H 'Content-Type: application/json' -d '{"display_name":"Pilot 1"}'
curl -X POST $API/api/customers/c-1042/statements -H "X-NarrAI-API-Key: $KEY" --data-binary @statement.xml
# or from the command line during a pilot
python -m manage import --bank kestrel --customer c-1042 --file statement.xml --name "Pilot 1"
```

| Format | What's handled |
|---|---|
| **camt.053** (ISO 20022 XML, versions .02–.08) | booked vs pending, reversals, creditor/debtor by direction, structured and unstructured purpose, opening balance. Parsed with `defusedxml`: DTDs, entity bombs and external entities are refused |
| **MT940** | `:61:`/`:86:` lines, German `?20–?29` purpose and `?32/?33` name sub-fields, reversals (`RC`/`RD`), IBAN computed from bank code + account in `:25:` |
| **CSV exports** | preamble lines, `;`/`,`, UTF-8 or Windows-1252, `-1.234,56` or `-1,234.56`, Soll/Haben columns, German or English column names, summary rows |

- **Re-imports are safe.** An exact re-upload is recognised by fingerprint; the same booking arriving in another format
  (worded differently) is recognised by date, amount, direction and category, matched by count so two identical coffees
  on one day both stay.
- The **IBAN is stored only masked and as a hash** (to match statements to accounts). Non-EUR entries are skipped and
  counted for now; files are limited to 5 MB / 50,000 entries.
- Every response summarises what happened: imported, duplicates, skipped (with reasons), categories and how many lines
  fell back to "Other".

### Categorisation

`backend/categorisation/` turns `PAYPAL *ZALANDO 1043-2231//BERLIN/DE` into *Zalando · Shopping*: it strips payment
processors, legal forms, terminal ids, cities and card numbers, then applies ordered keyword rules from
[`rules.json`](backend/categorisation/rules.json) (editable without code changes). Direction matters:

- money in with salary terms → **Income**; money back from a known shop → **Refunds** (money in, not income);
- own-account transfers (`Umbuchung`, `Tagesgeld`, credit-card settlement) → **Transfers** (neither spending nor income);
- cash machine withdrawals → **Cash**; unknown merchants → **Other**, with a cleaned name.

Every result records the rule that decided it (e.g. `rule:KINO`), so a bank can audit and correct it.
**Accuracy:** 60 / 60 on a labelled set of realistic German statement lines (`tests/test_categorisation.py`). Those
lines were written alongside the rules, so this shows the rules work as designed, not accuracy on unseen data; a pilot
should measure it on anonymised real statements.

## Security and GDPR

| Control | What it does |
|---|---|
| **Session revocation** | Sign-out revokes the token server-side; banks can sign a customer out everywhere (tokens carry a per-customer session generation, so there is no clock-resolution gap) |
| **Rate limits** | Session creation 10/min, failed authentication 20/min per client (guessing, credential stuffing), chat 20/min per customer (model cost), uploads 30/min per bank, exports 5/min; `429` with `Retry-After`. In-memory per process: several API replicas need a shared store (e.g. Redis) |
| **Audit log** | Append-only `audit_events`: sessions, sign-outs, budget changes, imports, provisioning, exports, erasure, API-key and retention operations. Identifiers and counts only (no names, amounts, IBANs or IP addresses), with the request id. `python -m manage audit --bank …` or `GET /api/audit` |
| **API headers** | `Cache-Control: no-store` on all financial data, `nosniff`, `X-Frame-Options: DENY`, `CSP default-src 'none'`, `Referrer-Policy: no-referrer`, request ids (`X-Request-ID`), HSTS when `NARRAI_HTTPS=1` |
| **Web app headers** | `proxy.ts` sets a per-request nonce CSP: only Next's own scripts run (`strict-dynamic`, no `unsafe-eval` in production); the API is the only other origin; framing denied. Styles allow inline attributes because the chart library needs them |
| **GDPR access / portability** | Customers download their data ("My data"); banks export it for access requests |
| **GDPR erasure** | `DELETE /api/customers/{ref}` removes the customer, accounts, transactions and budgets, ends their sessions and clears cached stories; the audit trail keeps only the pseudonymous id to stay accountable |
| **Retention** | `python -m manage purge --bank kestrel --months 24` deletes older transactions and expired sign-out records |

## Data model

Postgres in production, SQLite for quick local development; the schema is versioned with Alembic
(`backend/migrations/`) and applied with `alembic upgrade head` (the Docker image does this on start).

```
customers (tenant_id, external_ref) ─┬─ accounts ── transactions (booked_on, merchant, category, amount, direction)
                                      └─ budgets (category, amount)
```

- **Every table carries `tenant_id`** (the bank) and every query filters on bank *and* customer; all SQL lives
  in `backend/repository.py`. Writes re-check that the customer belongs to the bank, so a mismatched
  bank/customer pair can neither read nor change another bank's data (covered by tests).
- Amounts are `NUMERIC(12,2)` and positive; `direction` (`in`/`out`) says which way money moved, so refunds and
  transfers from savings are money in without being income. Database constraints reject negative amounts, unknown
  directions and zero or negative budgets.
- The test suite builds its database with the real migrations and fails if `models.py` and the migrations
  ever disagree. CI runs it on SQLite and Postgres.
- `python -m seed` loads the same demo customers for every bank (sample account plus three synthetic personas).

## Budgets

Customers set monthly limits per spending category; progress is calculated by code
(`backend/analytics/budgets.py`), never by the LLM:

- spent vs. budget, remaining, status (`on_track` < 80% ≤ `close` ≤ 100% < `over`),
  a month-end projection while the month is in progress, and how many of the last 3 months stayed within;
- suggested amounts from typical spending (average of the previous 3 months, rounded up to €5),
  with one-click "Create this budget" from the recommendations;
- over-budget cards top the insight feed, and the chat answers "Am I within my budgets?" with the
  exact over/left amounts (a guardrail rejects any other "€X over" figure).

Budgets are stored in the database, scoped by bank and customer. API: `GET /api/budgets?month=`, `PUT /api/budgets/{category}` `{"amount"}`, `DELETE /api/budgets/{category}`.

## Ask about my money (chat)

`POST /api/chat {"question", "month", "previous"}` answers questions from verified numbers only:

1. **Policy first** — investment, credit or other regulated advice is declined by code, before any model runs.
2. **Routing** — clear phrasings ("compare", "biggest payments", "save") route by keyword rules; the LLM
   decides only ambiguous questions. Categories, merchants and months must appear in the question
   (or continue the previous question) — the model cannot invent them.
3. **Calculation** — `analytics/queries.py` computes the answer with pandas (spending, top merchants,
   comparisons, largest payments, category breakdown, monthly average, income kept, unusual payments).
4. **Narration** — the LLM phrases the verified result; the guardrails reject unverified numbers,
   speculation, wrong directions and answers that don't name their topic, falling back to a template.

Every answer returns its source (`ai`, `template` or `policy`) and the facts behind it, shown in the UI
under "Show the numbers". Evaluate with `python -m evals.run_chat_eval` (30 labelled questions).

## Narration evaluation

`backend/evals/run_eval.py` runs the full pipeline over seeded synthetic customers
(`analytics/synthetic.py`: young professional, family, student) and reports how often
AI sentences pass the guardrails, why they were rejected, latency, and — the key number —
**how many unverified numbers reached a user** (must always be 0).

```bash
cd backend && ../venv/bin/python -m evals.run_eval --seeds 3 --months 6
```

Reports are written to `backend/evals/reports/` as JSON and Markdown.

The guardrails check every AI sentence for: numbers not in the verified facts, speculative or
causal language, missing key entities (category, top merchant), and **wrong direction**
(e.g. "€17.66, down from €16.32", or "went up" when spending fell).

## Accessibility and resilience

- Text colours meet WCAG AA contrast (4.5:1), and bank themes are validated for it on load.
- Status is never colour-only (icon + label); charts have text descriptions and a table view.
- Visible keyboard focus in the bank's colour, a "Skip to main content" link, and the chat panel closes
  with Escape and returns focus to its launcher. Animations respect "reduce motion".
- Layout works from 375px phones upward with no sideways scrolling.
- Loading shows a skeleton of the page; failures show a clear message with "Try again" (the story can be
  retried on its own without reloading the numbers).

## Tests

```bash
cd backend && ../venv/bin/python -m pytest
```
