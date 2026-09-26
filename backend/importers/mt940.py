"""SWIFT MT940 statements, including the German structured :86: purpose fields.

    :25:  account (BLZ/account or IBAN)      :60F: opening balance
    :61:  statement line (date, D/C, amount) :86:  details (?20-?29 purpose, ?32/?33 name)
"""

import re
from datetime import date
from decimal import Decimal

from importers.base import ParsedStatement, StatementEntry, StatementError

TAG = re.compile(r"^:(\d{2}[A-Z]?):", re.MULTILINE)
# YYMMDD [MMDD] (C|D|RC|RD) [funds code] amount with comma decimals
LINE_61 = re.compile(r"^(\d{6})(\d{4})?(RC|RD|C|D)[A-Z]?(\d+,\d{0,2})")
BALANCE = re.compile(r"^([CD])(\d{6})([A-Z]{3})(\d+,\d{0,2})")


def _amount(text: str) -> Decimal:
    return Decimal(text.replace(",", "."))


def _yymmdd(text: str) -> date:
    return date(2000 + int(text[:2]), int(text[2:4]), int(text[4:6]))


def german_iban(bank_code: str, account: str) -> str | None:
    """IBAN from a German bank code (BLZ) and account number, as MT940 :25: often gives them."""
    if not (bank_code.isdigit() and len(bank_code) == 8 and account.isdigit() and len(account) <= 10):
        return None
    bban = bank_code + account.zfill(10)
    check = 98 - int(bban + "131400") % 97  # "DE" = 13 14, then "00"
    return f"DE{check:02d}{bban}"


def _details(text: str) -> tuple[str, str]:
    """(counterparty, purpose) from a :86: field; handles German ?-subfields and plain text."""
    flat = text.replace("\r", "").replace("\n", "")
    if "?" not in flat:
        return "", flat.strip()
    fields = {}
    for code, value in re.findall(r"\?(\d{2})([^?]*)", flat):
        fields.setdefault(code, []).append(value)
    # Sub-fields are fixed-width continuations (27 characters, often cut mid-word): join without spaces.
    purpose = "".join(v for code in [f"{i:02d}" for i in range(20, 30)] + [f"{i:02d}" for i in range(60, 64)]
                      for v in fields.get(code, []) if v)
    name = "".join(fields.get("32", []) + fields.get("33", []))
    return name.strip(), purpose.strip()


def parse(data: bytes) -> ParsedStatement:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")  # older German MT940 exports
    if ":61:" not in text and ":20:" not in text:
        raise StatementError("Not an MT940 statement (no :20: or :61: fields).")

    # Split into (tag, value) fields; values can span lines.
    positions = [(m.start(), m.end(), m.group(1)) for m in TAG.finditer(text)]
    fields = [(tag, text[end:(positions[i + 1][0] if i + 1 < len(positions) else len(text))].strip())
              for i, (_, end, tag) in enumerate(positions)]

    parsed = ParsedStatement(format="MT940", iban=None, opening_balance=None)
    pending: dict | None = None

    def flush():
        nonlocal pending
        if pending:
            parsed.entries.append(StatementEntry(**pending))
        pending = None

    for tag, value in fields:
        if tag == "25" and parsed.iban is None:
            compact = value.replace(" ", "").split("EUR")[0]
            if re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", compact):
                parsed.iban = compact
            elif "/" in compact:
                bank_code, account = compact.split("/", 1)
                parsed.iban = german_iban(bank_code, account)
        elif tag == "60F" and parsed.opening_balance is None:
            match = BALANCE.match(value)
            if match:
                amount = _amount(match.group(4))
                parsed.opening_balance = -amount if match.group(1) == "D" else amount
        elif tag == "61":
            flush()
            match = LINE_61.match(value.replace("\n", ""))
            if not match:
                parsed.skip("unreadable :61: line")
                continue
            mark = match.group(3)
            if mark in ("RC", "RD"):
                parsed.skip("reversal")
                continue
            amount = _amount(match.group(4))
            pending = {
                "booked_on": _yymmdd(match.group(1)),
                "amount": amount if mark == "C" else -amount,
                "counterparty": "",
                "description": "",
            }
        elif tag == "86" and pending is not None:
            pending["counterparty"], pending["description"] = _details(value)
    flush()

    if not parsed.entries and not parsed.skipped:
        raise StatementError("MT940 file contains no statement lines.")
    return parsed
