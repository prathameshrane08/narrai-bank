"""Statement import: parse → categorise → fingerprint → store (via the repository)."""

import hashlib
from collections import Counter
from decimal import Decimal

from categorisation import categorise
from importers import parse_statement
from repository import CustomerRef, Repository


def mask_iban(iban: str | None) -> str:
    if not iban:
        return "Imported account"
    compact = iban.replace(" ", "").upper()
    return f"{compact[:4]} •••• •••• {compact[-4:]}"


def iban_hash(iban: str | None) -> str | None:
    return hashlib.sha256(iban.replace(" ", "").upper().encode()).hexdigest() if iban else None


def import_statement(repo: Repository, customer: CustomerRef, data: bytes) -> dict:
    parsed = parse_statement(data)

    rows, categories, rules_used = [], Counter(), Counter()
    seen: Counter = Counter()
    skipped = dict(parsed.skipped)
    for entry in parsed.entries:
        if entry.currency != "EUR":
            skipped["currency other than EUR"] = skipped.get("currency other than EUR", 0) + 1
            continue
        if entry.amount == 0:
            skipped["zero amount"] = skipped.get("zero amount", 0) + 1
            continue

        result = categorise(entry.counterparty, entry.description, entry.amount)
        # Identical entries in one file (two coffees, same day, same price) get distinct fingerprints.
        identity = f"{entry.booked_on}|{entry.amount}|{entry.counterparty}|{entry.description}"
        seen[identity] += 1
        fingerprint = hashlib.sha256(f"{identity}|{seen[identity]}".encode()).hexdigest()

        rows.append({
            "booked_on": entry.booked_on,
            "merchant": result.merchant[:200],
            "category": result.category,
            "amount": abs(entry.amount).quantize(Decimal("0.01")),
            "direction": result.direction,
            "description": entry.description[:500] or None,
            "fingerprint": fingerprint,
        })
        categories[result.category] += 1
        rules_used["fallback" if result.rule == "fallback" else "matched"] += 1

    imported, duplicates, account = repo.import_entries(
        customer, iban_hash(parsed.iban), mask_iban(parsed.iban), parsed.opening_balance, rows
    )
    return {
        "format": parsed.format,
        "account": account,  # the account the rows were stored on (CSV exports carry no IBAN)
        "entries": len(parsed.entries),
        "imported": imported,
        "duplicates": duplicates,
        "skipped": skipped,
        "categories": dict(categories.most_common()),
        "uncategorised": rules_used["fallback"],
    }
