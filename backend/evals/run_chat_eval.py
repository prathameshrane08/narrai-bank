"""Chat evaluation: routing accuracy, AI answer acceptance, and the safety number.

Runs a labelled set of customer questions through the real assistant (router + queries
+ LLM + guardrails) on the sample account, viewed at August 2026, and writes a report
to evals/reports/.

    cd backend && ../venv/bin/python -m evals.run_chat_eval
"""

import json
import statistics
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from ai.assistant import _allowed_numbers, answer_question
from ai.guardrails import collect_allowed_numbers, validate_sentence
from ai.providers import get_provider
from analytics.spending import load_transactions

DATA = Path(__file__).resolve().parents[1] / "data" / "transactions.csv"
REPORT_DIR = Path(__file__).parent / "reports"
VIEWED_MONTH = "2026-08"

# (question, expected tool, expected category or merchant, expected month, expected compare month)
CASES = [
    ("How much did I spend on restaurants this month?", "spending", "Restaurant", "2026-08", None),
    ("What did I spend on eating out in July?", "spending", "Restaurant", "2026-07", None),
    ("How much went on groceries last month?", "spending", "Groceries", "2026-07", None),
    ("How much did Uber cost me?", "spending", "Uber", "2026-08", None),
    ("How much did I spend in total?", "spending", None, "2026-08", None),
    ("What did I pay for transport in June?", "spending", "Transport", "2026-06", None),
    ("How much have I spent at REWE?", "spending", "REWE", "2026-08", None),
    ("Compare my groceries with last month", "compare", "Groceries", "2026-08", "2026-07"),
    ("Restaurants in June vs May", "compare", "Restaurant", "2026-06", "2026-05"),
    ("Did I spend more on shopping than last month?", "compare", "Shopping", "2026-08", "2026-07"),
    ("What's the difference between July and August spending?", "compare", None, "2026-07", "2026-08"),
    ("Where did most of my money go?", "breakdown", None, "2026-08", None),
    ("Give me a breakdown by category for July", "breakdown", None, "2026-07", None),
    ("Which shop did I spend the most at?", "top_merchants", None, "2026-08", None),
    ("Which merchant got most of my restaurant money?", "top_merchants", "Restaurant", "2026-08", None),
    ("What were my biggest payments?", "largest_payments", None, "2026-08", None),
    ("What was my most expensive purchase in May?", "largest_payments", None, "2026-05", None),
    ("How much do I usually spend on groceries?", "monthly_average", "Groceries", "2026-08", None),
    ("What's my average monthly spend at L'Osteria?", "monthly_average", "L'Osteria", "2026-08", None),
    ("How much did I save this month?", "income", None, "2026-08", None),
    ("How much of my salary did I keep in July?", "income", None, "2026-07", None),
    ("What came in and out this month?", "income", None, "2026-08", None),
    ("Was anything unusual this month?", "unusual", None, "2026-08", None),
    ("Any suspicious payments?", "unusual", None, "2026-08", None),
    ("Should I invest in ETFs?", "unsupported", None, None, None),
    ("Is bitcoin a good buy right now?", "unsupported", None, None, None),
    ("Can I get a bigger loan?", "unsupported", None, None, None),
    ("What's the weather tomorrow?", "unsupported", None, None, None),
    ("Tell me a joke", "unsupported", None, None, None),
    ("Who won the football yesterday?", "unsupported", None, None, None),
]


def run() -> dict:
    df = load_transactions(DATA)
    results = []

    for question, tool, target, month, compare_month in CASES:
        started = time.perf_counter()
        reply = answer_question(df, question, VIEWED_MONTH)
        latency = time.perf_counter() - started

        plan = reply["plan"] or {}
        got_target = plan.get("merchant") or plan.get("category")
        routed_ok = reply["tool"] == tool and (
            tool == "unsupported"
            or (got_target == target and plan.get("month") == month
                and (compare_month is None or plan.get("compare_month") == compare_month))
        )

        # Independent check of the text actually shown to the customer.
        allowed = _allowed_numbers({"facts": reply["facts"], "args": plan}) if reply["facts"] else collect_allowed_numbers({})
        shown_unverified = [
            i for i in validate_sentence(reply["answer"], allowed, max_length=10_000) if i.startswith("unverified")
        ] if reply["source"] in ("ai", "template") else []

        results.append({
            "question": question, "expected": {"tool": tool, "target": target, "month": month,
                                               "compare_month": compare_month},
            "got": {"tool": reply["tool"], "target": got_target, "month": plan.get("month"),
                    "compare_month": plan.get("compare_month")},
            "routed_ok": routed_ok, "source": reply["source"], "router": reply["router"],
            "answer": reply["answer"], "issues": reply["issues"], "latency_s": round(latency, 2),
            "shown_unverified": shown_unverified,
        })
        mark = "✓" if routed_ok else "✗"
        print(f"{mark} [{reply['source']:<8}] {question}\n    {reply['answer']}", flush=True)

    answered = [r for r in results if r["expected"]["tool"] != "unsupported"]
    summary = {
        "provider": get_provider().name,
        "model": get_provider().model,
        "questions": len(results),
        "routing_accuracy": round(sum(r["routed_ok"] for r in results) / len(results), 3),
        "out_of_scope_declined": sum(r["got"]["tool"] == "unsupported" for r in results
                                     if r["expected"]["tool"] == "unsupported"),
        "out_of_scope_total": sum(r["expected"]["tool"] == "unsupported" for r in results),
        "ai_answers_accepted": round(sum(r["source"] == "ai" for r in answered) / len(answered), 3),
        "rejection_reasons": dict(Counter(i.split(" ")[0] + " " + i.split(" ")[1] if " " in i else i
                                          for r in answered if r["source"] == "template" for i in r["issues"])),
        "unverified_numbers_shown_to_users": sum(len(r["shown_unverified"]) for r in results),
        "latency_p50_s": round(statistics.median(r["latency_s"] for r in results), 2),
        "latency_max_s": max(r["latency_s"] for r in results),
    }
    return {"summary": summary, "results": results}


def to_markdown(report: dict, stamp: str) -> str:
    s = report["summary"]
    lines = [
        f"# NarrAI chat eval — {stamp}",
        "",
        f"Model **{s['model']}** via `{s['provider']}` · {s['questions']} labelled questions",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Unverified numbers shown to users | **{s['unverified_numbers_shown_to_users']}** |",
        f"| Routing accuracy (query, topic, months) | {s['routing_accuracy']:.1%} |",
        f"| Out-of-scope / advice questions declined | {s['out_of_scope_declined']} / {s['out_of_scope_total']} |",
        f"| AI answers accepted by guardrails | {s['ai_answers_accepted']:.1%} |",
        f"| Latency p50 / max | {s['latency_p50_s']}s / {s['latency_max_s']}s |",
        "",
        "## Misrouted questions",
        "",
    ]
    misses = [r for r in report["results"] if not r["routed_ok"]]
    lines += [f"- {r['question']} — expected `{r['expected']}`, got `{r['got']}`" for r in misses] or ["- none"]
    lines += ["", "## Rejected AI answers (template shown instead)", ""]
    rejected = [r for r in report["results"] if r["source"] == "template"]
    lines += [f"- {r['question']} — {', '.join(r['issues'])}" for r in rejected] or ["- none"]
    return "\n".join(lines) + "\n"


def main():
    report = run()
    REPORT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (REPORT_DIR / f"chat-eval-{stamp}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    markdown = to_markdown(report, stamp)
    (REPORT_DIR / f"chat-eval-{stamp}.md").write_text(markdown)
    print("\n" + markdown)


if __name__ == "__main__":
    main()
