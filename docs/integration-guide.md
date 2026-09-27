# NarrAI integration guide for banks

NarrAI turns a customer's transactions into a short, verified story, ranked insights, budgets and a
chat that answers questions about their money. Every number is calculated by NarrAI's analytics; the
language model only words it, and a guardrail rejects any sentence that states something the numbers
don't support.

This guide is for the bank's developers. The machine-readable API specification is
[`openapi.json`](openapi.json) (also browsable at `/docs` on a running NarrAI instance).

---

## 1. How the pieces fit

```
                    ┌──────────── bank infrastructure ────────────┐
 customer ──login──►│ bank app / online banking                    │
                    │      │                                       │
                    │ bank backend ──X-NarrAI-API-Key──────────────┼──► NarrAI API ──► analytics + model
                    │   • provision customers                      │        │
                    │   • upload statements (camt.053/MT940/CSV)   │        ▼
                    │   • get a session for a signed-in customer   │    Postgres
                    └──────────────────────────────────────────────┘
 customer's app ──Authorization: Bearer <session>──► NarrAI API (dashboard, story, chat, budgets)
```

- **NarrAI never sees customer passwords.** The bank authenticates its customer; the bank's backend then
  asks NarrAI for a 30-minute session for that customer.
- **Server-to-server calls** use the bank's API key. **Customer-facing calls** use the session token.
- The bank's identity always comes from the key or the session, never from a header a browser could set.

## 2. Onboarding checklist

| Step | Who | What |
|---|---|---|
| 1 | NarrAI | Create the bank's white-label config (`backend/tenants/<bank>.json`): display name, assistant name, logo, colours (validated for WCAG AA contrast), account label, legal footer, where regulated-advice questions are referred, feature flags (`story`, `chat`, `insights`) |
| 2 | NarrAI | Issue an API key: `python -m manage api-key create --bank <bank> --name "<system>"`. It is shown once; transfer it through the bank's secret manager, never email |
| 3 | Bank | Store the key server-side only. Never ship it to a browser or mobile app |
| NarrAI | For the white-label web app: set the bank's `app_url` (e.g. `https://insights.bank.de`) and deploy the web app there (§5a) |
| 4 | Bank | Allow-list the NarrAI API host in outbound firewalls; send the web app origin(s) to NarrAI for CORS (`NARRAI_FRONTEND_ORIGINS`) |
| 5 | Both | Agree data retention (default proposal: 24 months) and the process for access and erasure requests (§8) |
| 6 | Bank | Provision a test customer, upload a statement, create a session, and call `/api/dashboard` (§4) |

## 3. Authentication

| Caller | Header | Obtained from |
|---|---|---|
| Bank backend | `X-NarrAI-API-Key: nk_…` | NarrAI operator (step 2) |
| Customer app | `Authorization: Bearer <token>` | `POST /api/sessions`, called by the bank backend |

Sessions last 30 minutes (`expires_at` in the response). When one expires, calls return `401` with
`WWW-Authenticate: Bearer`; the bank backend creates a new session. A customer's sign-out
(`POST /api/sessions/current/revoke`) ends the token immediately. The bank can end **every** session of a
customer at once (lost phone, fraud, account closure) with
`POST /api/customers/{ref}/sessions/revoke-all`.

## 4. Bank endpoints

`$API` is the NarrAI base URL; `$KEY` the bank's API key. `customer_ref` is **the bank's own identifier**
for the customer (letters, digits, `.`, `_`, `:`, `-`; up to 80 characters). Use a pseudonymous id, not an
account number or name.

**Provision a customer** (idempotent; safe to call on every login):

```bash
curl -X PUT "$API/api/customers/c-1042" -H "X-NarrAI-API-Key: $KEY" \
     -H 'Content-Type: application/json' -d '{"display_name": "Anna"}'
# {"ref": "c-1042", "created": true}   → later calls return "created": false
```

**Upload a statement**: the file is the request body; the format is detected automatically.

```bash
curl -X POST "$API/api/customers/c-1042/statements" -H "X-NarrAI-API-Key: $KEY" \
     --data-binary @statement-2026-08.xml
```

```json
{"format": "camt.053", "account": "DE89 •••• •••• 3000", "entries": 10, "imported": 9, "duplicates": 0,
 "skipped": {"not booked (pending)": 1, "reversal": 1, "currency other than EUR": 1},
 "categories": {"Housing": 1, "Groceries": 1, "Shopping": 1, "Refunds": 1, "Transfers": 1, "Cash": 1,
                "Subscriptions": 1, "Restaurant": 1, "Income": 1}, "uncategorised": 0}
```

`entries` counts booked entries read from the file; `imported` + `duplicates` + the currency skips add up to it.
Pending entries and reversals are reported under `skipped` but never counted as entries.

| Format | Notes |
|---|---|
| camt.053 (ISO 20022 XML, .02–.08) | Only booked entries; reversals skipped. DTDs/entities are refused for safety |
| MT940 | German `?20–?33` sub-fields supported; IBAN derived from bank code and account number in `:25:` |
| CSV export | `;` or `,`, German or English numbers and column names, preamble lines, Soll/Haben columns |

- **Re-sending is safe**: an identical file imports nothing new, and the same booking sent in another format
  (e.g. camt.053 and MT940 for one account) is recognised and not counted twice.
- Limits: 5 MB and 50,000 entries per file; EUR only for now (other currencies are skipped and counted).
- Only the masked IBAN and a hash are stored; statements for the same IBAN land on the same account.

**Create a session** for a customer the bank has just signed in:

```bash
curl -X POST "$API/api/sessions" -H "X-NarrAI-API-Key: $KEY" \
     -H 'Content-Type: application/json' -d '{"customer_ref": "c-1042"}'
# {"token": "eyJ…", "token_type": "Bearer", "expires_at": "2026-09-26T20:36:00+00:00",
#  "customer": {"ref": "c-1042", "name": "Anna"}}
```

**Other bank endpoints**

| Endpoint | Purpose |
|---|---|
| `POST /api/customers/{ref}/sessions/revoke-all` | End all of the customer's sessions (`204`) |
| `GET /api/customers/{ref}/export` | Everything stored about the customer (access and portability requests) |
| `DELETE /api/customers/{ref}` | Erase the customer and all their data; returns counts removed |
| `GET /api/audit?customer_ref={ref}` | The bank's audit trail (identifiers and counts only) |

## 5. Customer app endpoints

Call these with the customer's session token. Two ways to use them:

- **Your own app (recommended today):** render NarrAI's data in the bank's app or online banking, using the
  endpoints below. Everything is supported.
- **NarrAI's white-label web app:** the ready-made app in your brand, opened from your app with a one-time
  launch code (§5a). No customer-app code needed on your side.

### 5a. Launching the white-label web app

Two steps on the bank's side, one server call and one URL to open:

```bash
# 1. Bank backend, after the customer has signed in to the bank's app:
curl -X POST "$API/api/launch-codes" -H "X-NarrAI-API-Key: $KEY" \
     -H 'Content-Type: application/json' -d '{"customer_ref": "c-1042"}'
# {"launch_url": "https://insights.bank.de/launch?code=4GNC…", "expires_at": "…"}

# 2. The bank app opens launch_url (browser tab or in-app web view) within 60 seconds.
```

What happens next:

```
bank app ──opens──► https://insights.bank.de/launch?code=…
                      web app server ──code + client secret──► POST /api/launch-codes/exchange
                                     ◄── session (30 min)
                      sets an httpOnly, Secure, SameSite=Lax cookie, redirects to /app (code leaves the URL)
browser  ──same-site calls──► web app server ──Authorization: Bearer──► NarrAI API
```

- **The code works once and for 60 seconds**, is stored only as a hash, and can only be exchanged by the web
  app's server (it must present `NARRAI_WEBAPP_SECRET`), so a leaked link is useless.
- **The session never reaches page scripts**: it lives in an httpOnly cookie; the web app's server adds it to
  API calls and only forwards the customer-app endpoints. Writes need an anti-forgery header and a same-origin
  request.
- **Sign-out** revokes the session at the API and clears the cookie. When the 30 minutes are over, the
  customer opens the web app from the bank app again.
- The web app runs at the bank's `app_url` (white-label config), ideally a subdomain of the bank such as
  `insights.bank.de`, so customers see the bank's domain and the cookie stays first-party.
- In an in-app web view, allow cookies for that domain.

### 5b. Customer app endpoints

| Endpoint | Returns |
|---|---|
| `GET /api/months` | Months with data, which can be compared (story and insights need a previous month), latest month |
| `GET /api/dashboard?month=YYYY-MM` | Verified facts, ranked insights, account summary, transactions, chart data. `facts` is `null` (with a `notice`) for a customer's first month |
| `GET /api/story?month=YYYY-MM` | Four sentences (what happened, why, what it means, what next), each marked `ai` or `template`. Slow on first request per month; then cached |
| `POST /api/chat` `{"question", "month", "previous"}` | An answer from verified numbers, its `source` (`ai`, `template`, `policy`) and the `facts` behind it. Investment, credit and loan questions are declined and referred to the bank's advisers |
| `GET/PUT/DELETE /api/budgets[/{category}]` | Budgets with progress, projection and suggestions |
| `GET /api/me/export` | The customer's own data as a JSON download |
| `POST /api/sessions/current/revoke` | Sign out |

**Show the source to customers.** Each story sentence and chat answer says whether the AI wrote it
(`ai`, already checked against the numbers) or it came from a verified template. The white-label app shows
"AI · verified" / "From facts"; we recommend the same transparency in the bank's own app.

## 6. Errors

All errors are JSON: `{"detail": "…"}`. Every response carries `X-Request-ID`; include it when contacting
support. You may send your own `X-Request-ID` to correlate with your logs.

| Status | Meaning | What to do |
|---|---|---|
| `401` | Missing, invalid, expired or revoked API key or session | Bank: check the key. App: get a new session |
| `403` | The session belongs to another bank, or the feature is switched off for this bank | Don't mix banks; check feature flags |
| `404` | Unknown customer (at *this* bank), month without data, or demo endpoint while demo mode is off | Provision first; check the month |
| `413` | Statement file over 5 MB | Split the statement by period |
| `422` | Invalid input, or the file isn't a readable statement (the message says why) | Fix the request or send us an anonymised sample |
| `429` | Rate limit reached | Wait `Retry-After` seconds, then retry |
| `503` | `/api/ready` only: the database is unreachable | Retry; page the operator if persistent |

## 7. Rate limits

| Limit | Allowance |
|---|---|
| Session creation | 10 per minute per API key (bank) / per client (demo) |
| Failed authentication | 20 per minute per client, then `429` |
| Chat | 20 questions per minute per customer |
| Statement uploads | 30 per minute per bank |
| Data exports | 5 per minute per customer or bank |

Bulk onboarding (uploading history for many customers) should pace uploads; tell us in advance and we
raise the upload limit for that window.

## 8. Security and data protection

| Topic | Bank | NarrAI |
|---|---|---|
| GDPR role | Controller: lawful basis, customer information, contract (Art. 28 DPA) | Processor, acting on the bank's instructions |
| Authentication of customers | Bank's own login and strong customer authentication | Never sees passwords; sessions are short-lived and revocable |
| Access / portability requests | Receives the request, calls `GET /api/customers/{ref}/export` | Returns all stored data within the call |
| Erasure requests | Calls `DELETE /api/customers/{ref}` | Deletes customer, accounts, transactions, budgets; ends sessions; audit keeps only a pseudonymous id |
| Retention | Sets the period | Runs `manage purge` on schedule |
| Data minimisation | Sends pseudonymous customer refs; statement files as they are | Stores masked IBAN + hash only; no names or amounts in logs, metrics or audit |
| Transport and storage | Calls over TLS only | TLS (HSTS), `Cache-Control: no-store`, security headers, CSP on the web app |
| Model | Chooses local (default: data stays on NarrAI's/the bank's servers) or an EU-hosted model | Evaluates every model change (see `docs/evaluation-report.md`) |
| Regulated advice | Offers advice through its own advisers | Declines investment, credit and loan questions by rule, referring to the bank |

## 9. Going live

- [ ] Production settings in place: `NARRAI_TOKEN_SECRET` from a secret manager, `NARRAI_HTTPS=1`,
      `NARRAI_DEMO_MODE=0`, `NARRAI_METRICS_TOKEN`, correct `NARRAI_FRONTEND_ORIGINS`.
- [ ] API key stored server-side; rotation procedure agreed (create new → switch → revoke old).
- [ ] Test customer provisioned, statement imported, dashboard/story/chat/budgets verified in the bank's app.
- [ ] Access and erasure requests tested end to end with the bank's DPO.
- [ ] Monitoring and alerts connected ([operations guide](operations.md)).
- [ ] Evaluation re-run on anonymised data from the bank's own statements; results reviewed together.
