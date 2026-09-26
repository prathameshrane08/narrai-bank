# NarrAI evaluation report

**Date:** 26 September 2026 · **Model:** Llama 3.2 3B (local, via Ollama) · **Hardware:** Apple-silicon laptop
**Principle under test:** *code calculates, AI narrates.* The model may word things; it must never
put a number, direction or claim in front of a customer that the analytics didn't produce.

---

## Summary

| | Result |
|---|---|
| **Unverified numbers shown to customers** | **0** (216 story sentences + 30 chat answers) |
| Story sentences accepted by the guardrails | 216 / 216 in the automated run |
| **Story sentences correct on human review** | **214 / 216**; the 2 errors are now caught by a new check (see §2.3) |
| Chat routing accuracy (query, topic, months) | **30 / 30** labelled questions |
| **Chat answers factually correct on human review** | **24 / 24** answered questions |
| Advice / off-topic questions declined | **6 / 6** (investment, crypto, loans are declined *before* any model runs) |
| Latency, local laptop | story p50 8.6 s (pre-written at startup) · chat p50 3.9 s |

**The honest reading:** the guardrails *guarantee* that no unverified number reaches a customer: that's
enforced by code, not measured by chance. What they cannot fully guarantee is that every *verified*
number is used in the right claim. Human review found 2 such errors in 216 story sentences (0.9%),
both of the same kind; a targeted check now rejects them. In this sample, no further errors remain;
with 216 sentences, the 95% upper bound on the remaining rate of such errors is about 1.4% (rule of three).

---

## 1. Method

**Data.** Synthetic, seeded transactions (`backend/analytics/synthetic.py`) for three personas:
young professional (Berlin), family of four (Munich), student (Hamburg). Each has rent, utilities,
subscriptions, variable spending with weekend habits, random spending spikes and one-off unusual
payments. 3 customers per persona, 12 months each; the chat evaluation uses the sample account.

**Story evaluation** (`python -m evals.run_eval --seeds 3 --months 6`): 54 monthly stories
(3 personas × 3 customers × 6 months) = 216 sentences. For each: analytics → LLM draft → guardrails
→ template fallback, then an independent re-check of the text that would be shown.

**Chat evaluation** (`python -m evals.run_chat_eval`): 30 labelled questions (24 answerable, 6 advice or
off-topic) with the expected query, topic and months; checks routing, guardrail acceptance and the
shown text.

**Human review.** Every one of the 216 story sentences and 30 chat answers was read against its
verified facts: amounts, directions, which month a figure belongs to, and whether the claim follows.

## 2. Story results

### 2.1 Automated

| Metric | Value |
|---|---|
| Stories fully written by the AI | 54 / 54 |
| Sentences accepted (what happened / why / meaning / next step) | 100% / 100% / 100% / 100% |
| Unverified numbers shown | 0 |
| Provider errors | 0 |
| Latency p50 / p95 | 8.6 s / 11.5 s |

### 2.2 Human review

- 214 / 216 sentences correct, including all 18 budget suggestions that state a saving
  ("a €X budget would have saved €Y"), each re-calculated by hand.
- **2 errors, same pattern, both when a category dropped to zero:**
  - *"…your average Shopping transaction was €32.14 last month, and you had **3 transactions this month**."*
    (Actual: 0 this month, 3 last month.)
  - *"…€21.68 last month, and you had **1 transaction this month**."* (Actual: 0 this month, 1 last month.)
- Minor wording (not counted as errors): "dm contributing €176.49 to €435.13" (means *went from … to*).
- Product observation: a category falling to €0 can become the month's headline; it's accurate but
  not the most useful story. The insight feed already words this better ("No restaurant spending").

### 2.3 Fix and re-check

A new guardrail rejects "N transactions this/last month" unless N is that month's verified count.
Re-running the guardrails over all 216 saved drafts: **exactly the 2 erroneous sentences are now
rejected** (and replaced by the verified template); all 214 correct sentences are still accepted.

## 3. Chat results

| Metric | Value |
|---|---|
| Routing accuracy | 30 / 30 |
| AI answers accepted by the guardrails | 24 / 24 |
| Factually correct (human review) | 24 / 24 |
| Advice / off-topic declined | 6 / 6 |
| Latency p50 / max | 3.9 s / 5.6 s |

Wording quality issues found on review (facts correct, phrasing not good enough for production):

- *"How much did I save?"* → correct amounts, but a garbled clause ("€425.68 was spent on €425.68").
- *"What came in and out this month?"* → mentions money out only, not the €2,850.00 salary.
- *"Difference between July and August?"* → "35.2%" is correct relative to August, but doesn't say so.

## 4. What the evaluations caught during development

Each of these was found by the evaluation suite or by reviewing its output, then fixed and
locked in with a test:

| Found | Example | Fix |
|---|---|---|
| Merchant changes lost their sign in the fact sheet | wrong "biggest contributor" in months where spending fell | facts state "up €X" / "down €X" |
| Speculation | "likely due to fewer transactions" | banned causal/speculative phrases |
| Scope drift | "share of *all* spending" for a category fact | category must be named |
| Wrong direction with correct numbers | "€17.66, **down** from €16.32" | direction check on comparisons |
| Wrong budget difference with correct numbers | "€149.50 is **€50.00 over**" (actual €99.50) | explicit over/left facts + check |
| Numbers above €999 wrongly rejected | "€2,424.32" | thousands-separator parsing |
| Answer without its topic | "€50.50 in July" (restaurant? total?) | chat answers must name the topic |
| Weak routing by the small model | most questions became "how much did I spend" | hybrid keyword + LLM routing |
| Wrong month for a count | "3 transactions this month" (was last month) | month-attribution check (§2.3) |

Progress on the same kind of run: story sentence acceptance rose from 87.5% to 100% (without loosening
any check), and chat routing from 86.7% to 100%.

## 5. Limitations

- **Synthetic data.** Real bank data (messy merchant strings, refunds, transfers, shared accounts)
  will surface new cases. A pilot should re-run both evaluations on anonymised real data.
- **Small samples.** 216 story sentences and 30 chat questions show the approach works; they are not a
  certification. A pilot evaluation should use thousands of sentences and a larger question set,
  including adversarial phrasing.
- **One model, one language.** Results are for Llama 3.2 3B in English. Every model change or new
  language (German first) needs its own evaluation run.
- **Human review is one reviewer.** A production process should have two independent reviewers and
  track agreement.
- **Guardrails check claims they know about.** New kinds of claims need new checks; the process
  (evaluate → review → add a targeted check → re-run) is what the table in §4 demonstrates.

## 6. Reproduce

```bash
cd backend
../venv/bin/python -m evals.run_eval --seeds 3 --months 6   # 54 stories
../venv/bin/python -m evals.run_chat_eval                    # 30 chat questions
../venv/bin/python -m pytest                                 # 62 tests, including every fix above
```

Reports are written to `backend/evals/reports/` (JSON with every draft, plus a Markdown summary).
