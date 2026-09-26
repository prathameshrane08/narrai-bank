"""Turn messy bank text into a clean merchant name and a spending category.

Real statement lines look like "PAYPAL *ZALANDO 1043-2231//BERLIN/DE". The categoriser
1. cleans the text (payment processors, legal forms, terminal ids, cities, card numbers),
2. applies ordered keyword rules from rules.json (editable by the bank, no code change),
3. uses the direction of the money for salary, refunds, own-account transfers and cash.

Deterministic on purpose: the same line always gets the same category, and every result
says which rule produced it, so a bank can audit and correct it.
"""

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

RULES_FILE = Path(__file__).parent / "rules.json"

LEGAL_FORMS = r"\b(GMBH|MBH|AG|SE|KG|KGAA|OHG|EK|E K|UG|GBR|CO|INC|LTD|LLC|SARL|S A R L|BV|NV|SA|EU|DEUTSCHLAND|GERMANY|DE)\b"
NOISE = [
    r"\bSAGT DANKE\b", r"\bDANKT\b", r"\bFIL(IALE)?\b", r"\bNR\b", r"\bZW\b", r"\bKARTE\b", r"\bKARTENNR\b",
    r"\bEC\b", r"\bPOS\b", r"\bTERMINAL\b", r"\bHELP\b", r"\bWWW\b", r"\bCOM\b", r"\bDE\b",
]
CITIES = r"\b(BERLIN|MUENCHEN|HAMBURG|KOELN|FRANKFURT|STUTTGART|DUESSELDORF|LEIPZIG|DORTMUND|ESSEN|BREMEN|DRESDEN|HANNOVER|NUERNBERG|LUXEMBOURG|DUBLIN|AMSTERDAM)\b"


@dataclass(frozen=True)
class Categorised:
    merchant: str
    category: str
    direction: str  # "in" or "out"
    rule: str  # which rule decided it, for audit (e.g. "rule:REWE", "income", "fallback")


def _translit(text: str) -> str:
    table = str.maketrans({"Ä": "AE", "Ö": "OE", "Ü": "UE", "ä": "AE", "ö": "OE", "ü": "UE", "ß": "SS"})
    return text.translate(table).upper()


def _normalise(text: str) -> str:
    """Upper-case words only: punctuation, digits and ids become spaces."""
    text = _translit(text)
    text = text.replace("'", "").replace("’", "")
    text = re.sub(r"[^A-Z0-9&+]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=1)
def rules() -> dict:
    data = json.loads(RULES_FILE.read_text())
    for rule in data["rules"]:
        rule["patterns"] = [re.compile(rf"(?<![A-Z0-9]){re.escape(_normalise(term))}(?![A-Z0-9])")
                            for term in rule["match"]]
    return data


def _has_term(text: str, terms: list[str]) -> bool:
    return any(re.search(rf"(?<![A-Z0-9]){re.escape(_normalise(term))}(?![A-Z0-9])", text) for term in terms)


def clean_merchant(counterparty: str) -> str:
    """Readable merchant name from a raw counterparty string (used when no rule names it)."""
    text = _translit(counterparty)
    text = re.split(r"//|/", text)[0]  # "REWE MARKT//BERLIN/DE" -> "REWE MARKT"
    text = re.sub(r"[*_]", " ", text)
    text = _normalise(text)
    for prefix in sorted(rules()["processor_prefixes"], key=len, reverse=True):
        text = re.sub(rf"^{re.escape(_normalise(prefix))}\b\s*", "", text)
    text = re.sub(LEGAL_FORMS, " ", text)
    text = re.sub(CITIES, " ", text)
    for pattern in NOISE:
        text = re.sub(pattern, " ", text)
    text = re.sub(r"\b[A-Z]*\d[A-Z0-9]*\b", " ", text)  # ids, terminal and card numbers
    words = [w for w in text.split() if len(w) > 1 or w == "&"]
    name = " ".join(words[:4])
    return name.title().replace("&", " & ").replace("  ", " ").strip() if name else ""


def categorise(counterparty: str, description: str, amount: Decimal) -> Categorised:
    config = rules()
    direction = "in" if amount > 0 else "out"
    counterparty_text = _normalise(clean_merchant(counterparty) + " " + counterparty)
    haystack = _normalise(f"{counterparty} {description}")

    matched, matched_term = None, ""
    for rule in config["rules"]:
        for term, pattern in zip(rule["match"], rule["patterns"]):
            if pattern.search(counterparty_text) or pattern.search(haystack):
                matched, matched_term = rule, term
                break
        if matched:
            break

    fallback_name = clean_merchant(counterparty) or clean_merchant(description) or "Unknown"
    merchant = (matched and matched["merchant"]) or fallback_name

    if _has_term(haystack, config["transfer_terms"]):
        return Categorised(merchant, "Transfers", direction, "transfer")

    if direction == "in":
        if _has_term(haystack, config["income_terms"]):
            return Categorised(merchant, "Income", "in", "income")
        if matched:
            # Money back from a shop or service is a refund: money in, but not income.
            return Categorised(merchant, "Refunds", "in", f"refund:{matched_term}")
        return Categorised(merchant, "Income", "in", "credit")

    if _has_term(haystack, config["cash_terms"]):
        return Categorised("Cash withdrawal", "Cash", "out", "cash")
    if matched:
        return Categorised(merchant, matched["category"], "out", f"rule:{matched_term}")
    return Categorised(merchant, "Other", "out", "fallback")
