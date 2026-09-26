"""Turns the verified fact sheet into a four-part financial story.

The LLM (local Llama via Ollama by default, see ai/providers.py) writes one
sentence per question. Each sentence is checked by the guardrails; anything that
fails, or any provider outage, falls back to a deterministic template built from
the same facts.
"""

import hashlib
import json
import logging
import re

from ai.guardrails import collect_allowed_numbers, validate_sentence
from ai.providers import get_provider
from observability import record_narration, track_llm

logger = logging.getLogger(__name__)

SECTIONS = ("what_happened", "why", "meaning", "next_step")

_story_cache: dict[str, dict] = {}


def _eur(value: float) -> str:
    return f"€{value:,.2f}"


def _moved(amount: float) -> str:
    return f"up {_eur(amount)}" if amount >= 0 else f"down {_eur(abs(amount))}"


def _fact_sheet(facts: dict) -> str:
    """Pre-formatted facts, so the model copies numbers and directions instead of computing them."""
    h = facts["headline"]
    p = facts["patterns"]
    category = h["category"]
    went = "went up" if h["direction"] == "increase" else "went down"

    lines = [
        f"Month: {facts['month_label']} (compared with {facts['previous_month_label']})",
        f"Category with the biggest change: {category}",
        f"Your {category} spending {went}: {_eur(h['previous'])} last month -> {_eur(h['current'])} this month "
        f"({_moved(h['change_amount'])})",
    ]
    if h["change_pct"] is not None:
        lines.append(f"Percent change: {abs(h['change_pct']):.1f}% ({'increase' if h['change_pct'] >= 0 else 'decrease'})")
    else:
        lines.append("Percent change: not applicable because nothing was spent last month. Do not state a percent.")
    lines.append(
        f"Your typical {category} spending (average of the previous {h['trailing_months']} months): "
        f"{_eur(h['trailing_average'])}"
    )

    if facts["drivers"]:
        top = facts["drivers"][0]
        lines.append(
            f"Biggest contributor to the change: {top['merchant']} "
            f"({_eur(top['previous'])} -> {_eur(top['current'])}, {_moved(top['change_amount'])})"
        )
        for other in facts["drivers"][1:3]:
            lines.append(
                f"Other merchant: {other['merchant']} ({_eur(other['previous'])} -> {_eur(other['current'])}, "
                f"{_moved(other['change_amount'])})"
            )

    lines += [
        f"Your {category} transactions: {p['transactions_current']} this month, {p['transactions_previous']} last month",
        f"Your average {category} transaction: {_eur(p['average_transaction_current'])} this month, "
        f"{_eur(p['average_transaction_previous'])} last month",
        f"Share of your {category} spending that happened on weekends: {p['weekend_share_pct']:.1f}%",
    ]

    if facts["recommendations"]:
        top = facts["recommendations"][0]
        lines.append(f"Top suggested action: {top['title']}. {top['detail']}")

    return "\n".join(f"- {line}" for line in lines)


# A worked example with made-up values, so the model learns the tone and structure.
# Its numbers are deliberately unlikely to appear in real facts; copying them fails the guardrails.
_EXAMPLE = """{
  "what_happened": "Your Entertainment spending went up by 312.4% in March 2031, reaching €207.13.",
  "why": "Kino Nord was the biggest contributor, going from €11.11 to €141.17.",
  "meaning": "81.9% of your Entertainment spending happened on weekends, across 7 transactions.",
  "next_step": "You could set a €55 monthly entertainment budget, which would have saved €152.13 this month."
}"""


def build_story_prompt(facts: dict) -> str:
    return f"""You are NarrAI, a friendly financial storyteller inside a banking app.

Rewrite the verified facts below into a short story for the user.

Verified facts:
{_fact_sheet(facts)}

Return a JSON object with exactly these keys, each holding ONE sentence:
- "what_happened": the category, whether it went up or down, the percent change and this month's amount.
- "why": name the biggest contributor exactly as listed, and its amounts.
- "meaning": one observed pattern about your {facts['headline']['category']} spending (weekend share, number of transactions or average transaction). Always name the category {facts['headline']['category']}.
- "next_step": the top suggested action, phrased as a friendly suggestion.

Example of the style (different customer, made-up numbers — never reuse them):
{_EXAMPLE}

Rules:
1. Use ONLY numbers that appear in the verified facts, written exactly as shown. Never calculate new numbers.
2. State facts only. Never explain causes: no "because", "due to", "likely", "probably" or "maybe". Do not predict the future.
3. Speak directly to the user with "you" and "your".
4. Keep each sentence under 35 words.
5. Output only the JSON object."""


def template_story(facts: dict) -> dict[str, str]:
    """Deterministic fallback sentences — always accurate, less fluent."""
    h = facts["headline"]
    p = facts["patterns"]
    category = h["category"].lower()
    verb = "increased" if h["direction"] == "increase" else "decreased"

    if h["change_pct"] is not None:
        what = (
            f"Your {category} spending {verb} by {abs(h['change_pct']):.1f}% in {facts['month_label']}, "
            f"reaching {_eur(h['current'])}."
        )
    else:
        what = f"You spent {_eur(h['current'])} on {category} in {facts['month_label']}, up from nothing last month."

    if facts["drivers"]:
        d = facts["drivers"][0]
        if d["change_amount"] > 0:
            why = (
                f"{d['merchant']} contributed the most to the increase, adding {_eur(d['change_amount'])} "
                f"compared with {facts['previous_month_label']}."
            )
        else:
            why = (
                f"{d['merchant']} accounted for the biggest drop, {_eur(abs(d['change_amount']))} less "
                f"than in {facts['previous_month_label']}."
            )
    else:
        why = f"No single merchant stood out in your {category} spending."

    meaning = (
        f"{p['weekend_share_pct']:.1f}% of your {category} spending happened on weekends, across "
        f"{p['transactions_current']} transactions averaging {_eur(p['average_transaction_current'])}."
    )

    if facts["recommendations"]:
        top = facts["recommendations"][0]
        next_step = f"{top['title']}: {top['detail']}"
    else:
        next_step = f"Your {category} spending looks steady — keep it up."

    return {"what_happened": what, "why": why, "meaning": meaning, "next_step": next_step}


def _required_terms(facts: dict) -> dict[str, tuple[str, ...]]:
    category = facts["headline"]["category"]
    top_merchant = facts["drivers"][0]["merchant"] if facts["drivers"] else None
    return {
        "what_happened": (category,),
        "why": (top_merchant,) if top_merchant else (),
        # Patterns are about the headline category, not all spending.
        "meaning": (category,),
        "next_step": (),
    }


def model_name() -> str:
    return get_provider().model


def _ask_llm(facts: dict) -> dict:
    with track_llm("story"):
        return get_provider().complete_json(build_story_prompt(facts))


def _cache_key(facts: dict) -> str:
    payload = json.dumps(facts, sort_keys=True) + model_name()
    return hashlib.sha256(payload.encode()).hexdigest()


# Allows a couple of words in between, e.g. "3 Restaurant transactions this month".
TRANSACTION_COUNT_PATTERN = re.compile(
    r"(\d+)\s+(?:[A-Za-z'&]+\s+){0,2}transactions?\s+(this|last)\s+month", re.IGNORECASE
)


def _transaction_counts_ok(text: str, facts: dict) -> bool:
    """'N transactions this/last month' must use that month's count, not the other month's."""
    counts = {
        "this": facts["patterns"]["transactions_current"],
        "last": facts["patterns"]["transactions_previous"],
    }
    return all(int(n) == counts[when.lower()] for n, when in TRANSACTION_COUNT_PATTERN.findall(text))


def assemble_story(facts: dict, draft: dict, ai_available: bool) -> dict:
    """Keep each AI sentence that passes the guardrails; replace the rest with templates."""
    fallback = template_story(facts)
    allowed = collect_allowed_numbers(facts)
    required = _required_terms(facts)

    sections = {}
    for name in SECTIONS:
        text = draft.get(name)
        text = text.strip() if isinstance(text, str) else ""
        # The headline sentence must move in the same direction as the verified change.
        direction = facts["headline"]["direction"] if name == "what_happened" else None
        issues = validate_sentence(text, allowed, required[name], direction) if text else ["not generated"]
        if text and not _transaction_counts_ok(text, facts):
            issues.append("wrong month for transaction count")

        if issues:
            if ai_available:
                logger.info("Rejected AI sentence for %s (%s): %r", name, ", ".join(issues), text)
            sections[name] = {"text": fallback[name], "source": "template", "issues": issues}
        else:
            sections[name] = {"text": text, "source": "ai", "issues": []}

    return {"sections": sections, "model": model_name(), "ai_available": ai_available}


def clear_story_cache() -> None:
    """Forget every cached story (e.g. after a customer's data is erased)."""
    _story_cache.clear()


def generate_story(facts: dict, use_cache: bool = True) -> dict:
    """Return {"sections": {name: {"text", "source", "issues"}}, "model", "ai_available"}."""
    key = _cache_key(facts)
    if use_cache and key in _story_cache:
        return _story_cache[key]

    ai_available = True
    try:
        draft = _ask_llm(facts)
    except Exception as exc:  # provider down, timeout, invalid JSON...
        logger.warning("LLM narration unavailable, using templates: %s", exc)
        ai_available = False
        draft = {}

    story = assemble_story(facts, draft, ai_available)
    record_narration("story", story["sections"])

    # Only cache successful AI runs, so a restarted Ollama gets picked up.
    if ai_available:
        _story_cache[key] = story
    return story


if __name__ == "__main__":
    from pathlib import Path

    from analytics.insights import build_facts
    from analytics.spending import load_transactions

    data = load_transactions(Path(__file__).resolve().parents[1] / "data" / "transactions.csv")
    print(json.dumps(generate_story(build_facts(data), use_cache=False), indent=2, ensure_ascii=False))
