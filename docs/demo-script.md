# NarrAI — 7-minute demo script for banks

**Audience:** a bank's digital, product or innovation team.
**Goal:** show that NarrAI turns transactions into explanations customers understand, *without* the AI
ever making up a number, and that it drops into the bank's own app under the bank's own brand.

---

## Before the meeting (10 minutes)

- [ ] Start the stack: `docker compose up --build` (or the two local processes from the README).
- [ ] Open http://localhost:8000/api/health and wait for `"warmup": {"status": "ready"}`.
      Stories are then pre-written, so nothing waits on the model during the demo.
- [ ] Use a **Chrome profile without extensions**. One extension on the dev machine overrode CSS
      layout classes; a clean profile avoids surprises.
- [ ] Start with **no budgets** (remove any in the Budgets panel) so you can create one live.
- [ ] Make sure the API runs with `NARRAI_DEMO_MODE=1` (Docker Compose sets it).
- [ ] Open http://localhost:3000 at 1440px wide and sign in as **Demo Customer**.
      Have a second tab on `?bank=kestrel`, also signed in.
- [ ] Close notifications and other apps; the chat answers in ~3–5 seconds on a laptop.

---

## 1. The problem (30 s)

> "Banking apps show balances, charts and long transaction lists. Customers still can't answer the
> simple question: *what happened with my money this month, and what should I do about it?*
> Generative AI could explain it, but no bank will let a model invent numbers in front of customers."

> If asked about sign-in: "In a live bank the customer is already signed in to the bank's app; the bank's
> backend asks NarrAI for a 30-minute session with its own API key. NarrAI never sees a password."

## 2. The story: code calculates, AI narrates (1 min)

**Show:** the account panel, then *"Your August 2026 in a nutshell"* (screenshot 01).

- Read the four questions aloud: *What happened? Why? What does it mean? What can I do next?*
- Point at the **AI · verified** badges: "Every number here was calculated by our analytics engine.
  The model only wrote the sentence, and a guardrail checked every number in it before it was shown."
- "If a sentence fails the check, the customer sees a plain, verified sentence instead,
  marked *From facts*. The customer never sees an unchecked number."

## 3. What else happened (1 min)

**Show:** the insight feed (screenshot 02).

- "Beyond the headline, NarrAI ranks what matters: an unusual €36.50 Uber payment (2.8× usual),
  categories that jumped, and how much of the salary was kept."
- Click **Explore transport →** to jump to the drill-down (screenshot 03).
  "Every insight is one click from the transactions behind it."

## 4. From insight to action: budgets (1 min)

**Show:** scroll to *What you can do next* → **Create this budget** on the €50 restaurant suggestion.

- "The €50 isn't made up: it's the customer's own typical spending, rounded up."
- Scroll to **Budgets** (screenshot 04): *Over budget*, €99.50 over, within budget 1 of the last 3 months.
- Scroll up: **Over your restaurant budget** is now the top card in the feed.
- "Customer goals drive what the app highlights, and the AI story stops suggesting a budget that already exists."

## 5. Ask about my money (1.5 min)

**Click:** *Ask about my money* (screenshot 05). Ask, in order:

1. **"Am I within my budgets?"** → then click **Show the numbers**.
   "This is the audit trail: the exact calculation behind every answer, visible to the customer."
2. **"And in July?"** → follow-up keeps the topic.
3. **"Should I invest in ETFs?"** → declined *by a fixed rule before any AI runs*, and referred to
   the bank's own advisers. "Regulated advice stays with the bank."

## 6. Your brand, not ours (45 s)

**Switch** to the Kestrel tab or use *Demo brand* in the footer (screenshots 06–07).

- "Each bank is one config file: name, logo, colours, assistant name, legal text, where advice
  questions are referred, and which features are on."
- "Themes are validated for WCAG AA contrast before they load, so a bank can't ship an unreadable app."

## 7. Why you can trust it (1 min)

Show the headline numbers from [`evaluation-report.md`](evaluation-report.md):

- **0 unverified numbers shown** across all evaluated stories and chat answers.
- **100% routing accuracy** on 30 labelled chat questions; **6 of 6** advice/off-topic questions declined.
- "The evaluation also *found* real problems during development, like a sentence that said
  'down' when spending went up, which is why we check direction, not just numbers."

## 8. How it runs (30 s)

- "The model runs locally by default: customer data never leaves the bank's servers.
  A bank can also plug in its own or an EU-hosted model."
- "Docker images, CI on every change, WCAG AA contrast, works on phones."

**Close:** "We'd like to run a pilot on anonymised transactions from one customer segment and
measure understanding and engagement against your current app."

---

## If something goes wrong

| Situation | What to say / do |
|---|---|
| Model slow or offline | Sentences show **From facts**: "This is the safety net working: verified wording, no AI." |
| Chat answer is plainer than expected | It fell back to the template because the AI draft failed a check. Click *Show the numbers*. |
| Page fails to load | The error screen has **Try again**; check `/api/health`. |
| Asked to show a different month | Use the month picker in the header; the last 2 months are pre-written. |

## Questions banks will ask — honest answers

- **"Can the AI hallucinate?"** It can *write* a wrong sentence; it can't *show* one with an unverified
  number, wrong direction, speculation or a wrong budget difference. Those are rejected and replaced.
  Framing errors a number check can't see are still possible; the evaluation suite measures them and
  each new check has come from one it found.
- **"Is this real customer data?"** No. It's synthetic data from three personas (young professional,
  family, student). Real transactions arrive via the bank's own feeds or PSD2 in a pilot.
- **"Where does data go?"** By default nowhere: the model runs locally (Ollama). Hosted models are optional.
- **"Which languages?"** English today. German is the next obvious step and needs its own evaluation run.
- **"Is it regulated advice?"** No. It explains the customer's own spending and suggests budgets; investment,
  credit and loan questions are declined and referred to the bank.
- **"What does integration look like?"** A REST API plus a white-label web app; a bank can use either.
  Authentication, Postgres and bank statement import (CAMT.053/MT940) are the next phase.
