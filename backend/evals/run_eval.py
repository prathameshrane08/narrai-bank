"""Narration evaluation: how often does the AI's wording survive the guardrails,
and does any unverified number ever reach the user?

Runs the full pipeline (synthetic data -> analytics -> LLM -> guardrails) over
personas x seeds x months and writes a JSON + Markdown report to evals/reports/.

    cd backend && ../venv/bin/python -m evals.run_eval --seeds 3 --months 6
"""

import argparse
import json
import statistics
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from ai.guardrails import collect_allowed_numbers, validate_sentence
from ai.providers import get_provider
from ai.storyteller import SECTIONS, _ask_llm, assemble_story
from analytics.insights import build_facts, comparable_months
from analytics.spending import prepare_transactions
from analytics.synthetic import PERSONAS, generate_transactions

REPORT_DIR = Path(__file__).parent / "reports"


def _issue_kind(issue: str) -> str:
    for prefix in ("unverified number", "wrong direction", "speculative phrase", "missing", "too long", "not generated", "empty"):
        if issue.startswith(prefix):
            return prefix
    return issue


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1)))
    return ordered[index]


def run(personas: list[str], seeds: int, months: int) -> dict:
    cases = []

    for persona in personas:
        for seed in range(seeds):
            df = prepare_transactions(generate_transactions(persona, seed=seed))
            for month in comparable_months(df)[-months:]:
                facts = build_facts(df, month)

                started = time.perf_counter()
                try:
                    draft, error = _ask_llm(facts), None
                except Exception as exc:  # count provider failures instead of aborting the run
                    draft, error = {}, f"{type(exc).__name__}: {exc}"
                latency = time.perf_counter() - started

                story = assemble_story(facts, draft, ai_available=error is None)

                # Independent re-check of what the user would actually see.
                allowed = collect_allowed_numbers(facts)
                shown_unverified = [
                    issue
                    for section in story["sections"].values()
                    for issue in validate_sentence(section["text"], allowed)
                    if issue.startswith("unverified number")
                ]

                cases.append(
                    {
                        "persona": persona,
                        "seed": seed,
                        "month": month,
                        "headline": f"{facts['headline']['category']} {facts['headline']['direction']}",
                        "latency_s": round(latency, 2),
                        "error": error,
                        "sections": {
                            name: {
                                "draft": draft.get(name) if isinstance(draft.get(name), str) else None,
                                "shown": section["text"],
                                "source": section["source"],
                                "issues": section["issues"],
                            }
                            for name, section in story["sections"].items()
                        },
                        "shown_unverified_numbers": shown_unverified,
                    }
                )
                accepted = sum(s["source"] == "ai" for s in story["sections"].values())
                print(f"{persona:<20} seed={seed} {month}  ai {accepted}/4  {latency:5.1f}s", flush=True)

    return {"cases": cases, "summary": summarise(cases)}


def summarise(cases: list[dict]) -> dict:
    total_sentences = len(cases) * len(SECTIONS)
    per_section = {
        name: sum(c["sections"][name]["source"] == "ai" for c in cases) / len(cases) if cases else 0.0
        for name in SECTIONS
    }
    reasons = Counter(
        _issue_kind(issue)
        for c in cases
        if not c["error"]
        for section in c["sections"].values()
        for issue in section["issues"]
    )
    latencies = [c["latency_s"] for c in cases if not c["error"]]
    accepted = sum(s["source"] == "ai" for c in cases for s in c["sections"].values())

    return {
        "provider": get_provider().name,
        "model": get_provider().model,
        "stories": len(cases),
        "sentences": total_sentences,
        "provider_errors": sum(bool(c["error"]) for c in cases),
        "ai_acceptance_rate": round(accepted / total_sentences, 3) if total_sentences else 0.0,
        "acceptance_by_section": {k: round(v, 3) for k, v in per_section.items()},
        "fully_ai_stories": sum(all(s["source"] == "ai" for s in c["sections"].values()) for c in cases),
        "rejection_reasons": dict(reasons.most_common()),
        "unverified_numbers_shown_to_users": sum(len(c["shown_unverified_numbers"]) for c in cases),
        "latency_p50_s": round(statistics.median(latencies), 2) if latencies else None,
        "latency_p95_s": round(_percentile(latencies, 95), 2) if latencies else None,
    }


def to_markdown(report: dict, stamp: str) -> str:
    s = report["summary"]
    lines = [
        f"# NarrAI narration eval — {stamp}",
        "",
        f"Model **{s['model']}** via `{s['provider']}` · {s['stories']} stories · {s['sentences']} sentences",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Unverified numbers shown to users | **{s['unverified_numbers_shown_to_users']}** |",
        f"| AI sentences accepted by guardrails | {s['ai_acceptance_rate']:.1%} |",
        f"| Stories fully written by AI | {s['fully_ai_stories']} / {s['stories']} |",
        f"| Provider errors | {s['provider_errors']} |",
        f"| Latency p50 / p95 | {s['latency_p50_s']}s / {s['latency_p95_s']}s |",
        "",
        "## Acceptance by section",
        "",
        *[f"- `{name}`: {rate:.1%}" for name, rate in s["acceptance_by_section"].items()],
        "",
        "## Why AI sentences were rejected",
        "",
        *([f"- {reason}: {count}" for reason, count in s["rejection_reasons"].items()] or ["- none"]),
        "",
        "## Sample rejections",
        "",
    ]
    samples = [
        (c, name, sec)
        for c in report["cases"]
        for name, sec in c["sections"].items()
        if sec["source"] == "template" and sec["draft"]
    ][:10]
    for case, name, section in samples:
        lines += [
            f"- **{case['persona']} {case['month']} · {name}** — {', '.join(section['issues'])}",
            f"  - AI draft: {section['draft']}",
            f"  - Shown instead: {section['shown']}",
        ]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--personas", nargs="+", default=list(PERSONAS), choices=list(PERSONAS))
    parser.add_argument("--seeds", type=int, default=2, help="synthetic customers per persona")
    parser.add_argument("--months", type=int, default=4, help="most recent months to narrate per customer")
    args = parser.parse_args()

    report = run(args.personas, args.seeds, args.months)

    REPORT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (REPORT_DIR / f"eval-{stamp}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    markdown = to_markdown(report, stamp)
    (REPORT_DIR / f"eval-{stamp}.md").write_text(markdown)

    print("\n" + markdown)


if __name__ == "__main__":
    main()
