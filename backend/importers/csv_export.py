"""CSV account exports as German banks produce them (and NarrAI's own simple format).

Handles: preamble lines before the header, ';' or ',' delimiters, UTF-8 or Windows-1252,
"-1.234,56" or "-1,234.56" amounts, separate debit/credit (Soll/Haben) columns, and
dd.mm.yyyy, dd.mm.yy or ISO dates. Columns are found by their (German or English) names.
"""

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from importers.base import ParsedStatement, StatementEntry, StatementError

ALIASES = {
    "date": ["buchungstag", "buchungsdatum", "datum", "date", "booking date", "valutadatum", "wertstellung"],
    "amount": ["betrag", "betrag (€)", "betrag (eur)", "betrag eur", "umsatz", "umsatz in eur", "amount"],
    "debit": ["soll", "soll (eur)", "debit"],
    "credit": ["haben", "haben (eur)", "credit"],
    "counterparty": [
        "beguenstigter/zahlungspflichtiger", "begünstigter/zahlungspflichtiger", "zahlungsempfänger*in",
        "zahlungspflichtige*r", "auftraggeber / begünstigter", "auftraggeber/empfänger", "empfänger",
        "name", "payee", "merchant", "counterparty", "auftraggeber / empfänger",
    ],
    "description": ["verwendungszweck", "buchungstext", "description", "purpose", "reference", "vorgang"],
    "currency": ["währung", "waehrung", "currency"],
    "category": ["category"],
}


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise StatementError("CSV file encoding not recognised.")


def parse_amount(text: str) -> Decimal:
    value = text.strip().replace("€", "").replace("EUR", "").replace(" ", "").replace(" ", "")
    if not value:
        raise InvalidOperation
    if "," in value and "." in value:
        # Whichever separator comes last is the decimal separator.
        value = value.replace(".", "").replace(",", ".") if value.rfind(",") > value.rfind(".") else value.replace(",", "")
    elif "," in value:
        value = value.replace(",", ".")
    return Decimal(value)


def parse_date(text: str) -> date:
    value = text.strip()
    for pattern in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    raise ValueError(value)


def _find_columns(header: list[str]) -> dict[str, int]:
    lowered = [re.sub(r"\s+", " ", h.strip().lower()) for h in header]
    found = {}
    for key, names in ALIASES.items():
        for name in names:
            if name in lowered:
                found[key] = lowered.index(name)
                break
    return found


def parse(data: bytes) -> ParsedStatement:
    text = _decode(data)
    lines = text.splitlines()
    if not lines:
        raise StatementError("CSV file is empty.")

    # The header is the first line naming a date column and an amount (or debit/credit) column.
    for index, line in enumerate(lines[:30]):
        delimiter = ";" if line.count(";") >= line.count(",") else ","
        header = next(csv.reader([line], delimiter=delimiter))
        columns = _find_columns(header)
        if "date" in columns and ("amount" in columns or ("debit" in columns and "credit" in columns)):
            break
    else:
        raise StatementError("No header row with a date and an amount column was found in the CSV.")

    parsed = ParsedStatement(format="CSV", iban=None, opening_balance=None)
    reader = csv.reader(io.StringIO("\n".join(lines[index + 1:])), delimiter=delimiter)
    simple_format = "category" in columns  # NarrAI's format: positive amounts, "Income" marks money in

    def cell(row, key):
        position = columns.get(key)
        return row[position].strip() if position is not None and position < len(row) else ""

    for row in reader:
        if not any(field.strip() for field in row):
            continue
        try:
            booked_on = parse_date(cell(row, "date"))
        except ValueError:
            parsed.skip("unreadable date or summary line")
            continue
        try:
            if "amount" in columns:
                amount = parse_amount(cell(row, "amount"))
            else:
                debit, credit = cell(row, "debit"), cell(row, "credit")
                amount = parse_amount(credit) if credit else -abs(parse_amount(debit))
        except InvalidOperation:
            parsed.skip("unreadable amount")
            continue
        if simple_format:
            amount = abs(amount) if cell(row, "category") == "Income" else -abs(amount)

        parsed.entries.append(
            StatementEntry(
                booked_on=booked_on,
                amount=amount,
                counterparty=cell(row, "counterparty"),
                description=cell(row, "description"),
                currency=cell(row, "currency") or "EUR",
            )
        )
    return parsed
