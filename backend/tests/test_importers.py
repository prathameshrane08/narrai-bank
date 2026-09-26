from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from importers import MAX_BYTES, StatementError, detect_format, parse_statement
from importers.csv_export import parse_amount
from importers.mt940 import german_iban

FIXTURES = Path(__file__).parent / "fixtures"


def read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_detects_formats():
    assert detect_format(read("statement.camt053.xml")) == "camt.053"
    assert detect_format(read("statement.mt940")) == "MT940"
    assert detect_format(read("statement-export.csv")) == "CSV"


def test_camt053():
    parsed = parse_statement(read("statement.camt053.xml"))
    assert (parsed.format, parsed.iban, parsed.opening_balance) == ("camt.053", "DE89370400440532013000", Decimal("1250.40"))
    assert parsed.skipped == {"not booked (pending)": 1, "reversal": 1}
    assert len(parsed.entries) == 10

    rent, salary = parsed.entries[0], parsed.entries[-1]
    assert (rent.booked_on, rent.amount, rent.counterparty) == (date(2026, 8, 1), Decimal("-890.00"), "Hausverwaltung Kiefer GmbH")
    assert (salary.amount, salary.counterparty) == (Decimal("2850.00"), "Arbeitgeber GmbH")  # debtor for money in
    assert parsed.entries[5].description.startswith("Bargeldauszahlung")  # falls back to AddtlNtryInf
    assert [e.currency for e in parsed.entries].count("USD") == 1


@pytest.mark.parametrize(
    "hostile",
    [
        # "Billion laughs": exponential entity expansion.
        b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]><Document>&b;</Document>',
        # External entity trying to read a local file.
        b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]><Document>&x;</Document>',
    ],
)
def test_hostile_xml_is_refused(hostile):
    with pytest.raises(StatementError):
        parse_statement(hostile)


def test_mt940_with_german_fields():
    parsed = parse_statement(read("statement.mt940"))
    assert parsed.iban == "DE89370400440532013000"  # computed from bank code + account in :25:
    assert parsed.opening_balance == Decimal("1250.40")
    assert parsed.skipped == {"reversal": 1}
    assert parsed.entries[0].counterparty == "BVG Berliner Verkehrsbetriebe"  # ?32 + ?33 joined
    assert parsed.entries[0].amount == Decimal("-49.00")
    assert parsed.entries[-1].amount == Decimal("2850.00")


def test_german_iban_check_digits():
    assert german_iban("37040044", "532013000") == "DE89370400440532013000"
    assert german_iban("not-a-blz", "123") is None


def test_german_csv_export():
    parsed = parse_statement(read("statement-export.csv"))
    assert len(parsed.entries) == 6
    assert parsed.skipped == {"unreadable date or summary line": 1}  # the "Summe" line
    amazon = parsed.entries[1]
    assert (amazon.amount, amazon.booked_on) == (Decimal("-1249.00"), date(2026, 8, 4))
    assert parsed.entries[4].amount == Decimal("320.00")


def test_csv_with_debit_credit_columns_and_english_numbers():
    data = b"Date,Payee,Debit,Credit\n2026-08-01,Shop,\"1,234.56\",\n2026-08-02,Employer,,\"2,000.00\"\n"
    parsed = parse_statement(data)
    assert [e.amount for e in parsed.entries] == [Decimal("-1234.56"), Decimal("2000.00")]


def test_narrai_sample_csv_keeps_income_positive():
    parsed = parse_statement((Path(__file__).parents[1] / "data" / "transactions.csv").read_bytes())
    salary = [e for e in parsed.entries if e.counterparty == "Arbeitgeber GmbH"]
    assert salary and all(e.amount > 0 for e in salary)
    assert all(e.amount < 0 for e in parsed.entries if e.counterparty != "Arbeitgeber GmbH")


@pytest.mark.parametrize("text, value", [
    ("-1.234,56", "-1234.56"), ("1,234.56", "1234.56"), ("12,5", "12.5"), ("-3.20 €", "-3.20"), ("1234", "1234"),
])
def test_amount_formats(text, value):
    assert parse_amount(text) == Decimal(value)


def test_limits_and_garbage():
    with pytest.raises(StatementError, match="larger"):
        parse_statement(b"x" * (MAX_BYTES + 1))
    with pytest.raises(StatementError):
        parse_statement(b"   ")
    with pytest.raises(StatementError, match="header"):
        parse_statement(b"hello,world\n1,2\n")
    with pytest.raises(StatementError, match="camt.053"):
        parse_statement(b"<html><body>not a statement</body></html>")
