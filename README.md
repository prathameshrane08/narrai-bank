# NarrAI Bank

An AI-powered banking dashboard that turns transactions into a short, verified story:

1. **What happened?** — "Your restaurant spending increased by 196.0%, reaching €149.50."
2. **Why did it happen?** — "L'Osteria contributed the most, adding €47.50."
3. **What does it mean?** — "100.0% of your restaurant spending happened on weekends."
4. **What can I do next?** — budgets, merchant savings, weekend patterns, unusual-payment alerts.

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

## Run it

Prerequisites: Python 3.11+, Node 20+, [Ollama](https://ollama.com) with `ollama pull llama3.2:3b`.

```bash
# backend (from the repo root)
python -m venv venv && source venv/bin/activate
pip install -r backend/requirements.txt
cd backend && uvicorn main:app --reload --port 8000

# frontend (second terminal)
cd frontend && npm install && npm run dev
```

Open http://localhost:3000. The first story for a month takes a few seconds (local LLM); it is cached afterwards.

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `NARRAI_DATA_FILE` | `backend/data/transactions.csv` | CSV with `date,merchant,category,amount`; rows with category `Income` are money in, all others are spending |
| `NARRAI_OPENING_BALANCE` | `1840.00` | Demo account balance before the first transaction |
| `NARRAI_LLM_PROVIDER` | `ollama` | `ollama` (local, data stays on the machine) or `openai_compatible` (vLLM, EU-hosted APIs, Azure OpenAI…) |
| `NARRAI_MODEL` | `llama3.2:3b` | Model name for the chosen provider |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama server |
| `NARRAI_LLM_BASE_URL` / `NARRAI_LLM_API_KEY` | – | Endpoint and key for `openai_compatible` |
| `NARRAI_LLM_TIMEOUT` | `120` | Seconds before falling back to templates |
| `NARRAI_OLLAMA_KEEP_ALIVE` | `30m` | How long Ollama keeps the model loaded between requests (avoids ~60s cold starts) |
| `NARRAI_WARMUP` | `1` | Load the model and pre-write each bank's latest stories at startup (`0` to disable) |
| `NARRAI_DB_PATH` | `backend/data/narrai.db` | SQLite file for budgets |
| `NARRAI_FRONTEND_ORIGINS` | `http://localhost:3000,...` | CORS origins |
| `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8000` | API URL used by the frontend |

## API

| Endpoint | Returns |
|---|---|
| `GET /api/health` | Liveness and startup warm-up progress (`idle`, `running`, `ready`, `failed`) |
| `GET /api/months` | Months that have a previous month to compare with |
| `GET /api/dashboard?month=YYYY-MM` | Verified facts, account summary, transactions and chart data (fast, no LLM) |
| `GET /api/story?month=YYYY-MM` | Four-part narrative with per-sentence source |
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

## Budgets

Customers set monthly limits per spending category; progress is calculated by code
(`backend/analytics/budgets.py`), never by the LLM:

- spent vs. budget, remaining, status (`on_track` < 80% ≤ `close` ≤ 100% < `over`),
  a month-end projection while the month is in progress, and how many of the last 3 months stayed within;
- suggested amounts from typical spending (average of the previous 3 months, rounded up to €5),
  with one-click "Create this budget" from the recommendations;
- over-budget cards top the insight feed, and the chat answers "Am I within my budgets?" with the
  exact over/left amounts (a guardrail rejects any other "€X over" figure).

Budgets are stored in SQLite (`NARRAI_DB_PATH`, default `backend/data/narrai.db`), scoped by tenant and
customer. API: `GET /api/budgets?month=`, `PUT /api/budgets/{category}` `{"amount"}`, `DELETE /api/budgets/{category}`.

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
