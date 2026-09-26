"""Checks that an LLM-written sentence only states verified facts.

"Code calculates, AI narrates": if the model invents or miscopies a number, adds
speculation, or drops the key entity, the sentence is rejected and the caller
falls back to a deterministic template.
"""

import re

NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)?")

# Words that signal causal guessing or predictions the facts cannot support.
BANNED_PHRASES = (
    "probably",
    "likely",
    "might be because",
    "because",
    "due to",
    "you will",
    "you'll",
    "expect",
    "perhaps",
    "maybe",
)

MAX_SENTENCE_LENGTH = 320

UP_WORDS = ("went up", "increase", "rose", "risen", "grew", "higher", "more than")
DOWN_WORDS = ("went down", "decrease", "fell", "fallen", "dropped", "lower", "less than")

# "€17.66 ... down from €16.32" or "increased from €37.50 to €42.70": the direction
# word must agree with the numbers it compares. An explicit "to €X" is the new value.
COMPARISON_PATTERN = re.compile(
    r"(?:€?\s?(?P<before>\d[\d,]*(?:\.\d+)?)%?[^€\d]{0,60}?)?"
    r"\b(?P<word>up|down|increased|decreased|rose|fell)\s+from\s+€?\s?(?P<old>\d[\d,]*(?:\.\d+)?)"
    r"(?:\s*%?\s*to\s+€?\s?(?P<after>\d[\d,]*(?:\.\d+)?))?",
    re.IGNORECASE,
)


def collect_allowed_numbers(facts: dict) -> set[float]:
    """Every number in the fact sheet, plus how it could reasonably be written."""
    allowed: set[float] = set()

    def visit(value):
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            number = abs(float(value))
            allowed.update({number, round(number, 1), round(number, 2), float(round(number))})
        elif isinstance(value, str):
            allowed.update(_numbers_in(value))
        elif isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(facts)
    return allowed


def _numbers_in(text: str) -> list[float]:
    # Drop thousands separators like "1,234.50" before extracting numbers.
    cleaned = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)
    return [float(n.replace(",", ".")) for n in NUMBER_PATTERN.findall(cleaned)]


def _to_number(raw: str) -> float:
    return float(raw.replace(",", ""))


def _direction_issues(text: str, expected_direction: str | None) -> list[str]:
    problems = []
    lowered = text.lower()

    for match in COMPARISON_PATTERN.finditer(text):
        new_raw = match["after"] or match["before"]
        if new_raw is None:
            continue
        new, old = _to_number(new_raw), _to_number(match["old"])
        says_up = match["word"].lower() in ("up", "increased", "rose")
        if new != old and says_up != (new > old):
            problems.append(f"wrong direction: {match.group(0).strip()}")

    if expected_direction == "increase" and any(word in lowered for word in DOWN_WORDS):
        problems.append("wrong direction: says down, facts say up")
    if expected_direction == "decrease" and any(word in lowered for word in UP_WORDS):
        problems.append("wrong direction: says up, facts say down")

    return problems


def validate_sentence(
    text: str,
    allowed_numbers: set[float],
    required_terms: tuple[str, ...] = (),
    expected_direction: str | None = None,
    max_length: int = MAX_SENTENCE_LENGTH,
) -> list[str]:
    """Return a list of problems; an empty list means the sentence is safe to show."""
    problems = []

    if not text or not text.strip():
        return ["empty"]

    if len(text) > max_length:
        problems.append("too long")

    for number in _numbers_in(text):
        if not any(abs(number - allowed) < 0.006 for allowed in allowed_numbers):
            problems.append(f"unverified number {number:g}")

    lowered = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lowered:
            problems.append(f"speculative phrase '{phrase}'")

    for term in required_terms:
        if term.lower() not in lowered:
            problems.append(f"missing '{term}'")

    problems += _direction_issues(text, expected_direction)

    return problems
