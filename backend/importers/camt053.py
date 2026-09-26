"""ISO 20022 camt.053 (BankToCustomerStatement), the XML statement German banks issue.

Works across message versions (camt.053.001.02 – .08) by ignoring the namespace.
Parsed with defusedxml: DTDs, entity expansion and external entities are rejected.
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from defusedxml import ElementTree as SafeET

from importers.base import ParsedStatement, StatementEntry, StatementError


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(element, *path):
    """Follow a path of local tag names, ignoring namespaces; None if any step is missing."""
    for name in path:
        if element is None:
            return None
        element = next((c for c in element if _local(c.tag) == name), None)
    return element


def _children(element, name):
    return [c for c in element if _local(c.tag) == name] if element is not None else []


def _text(element, *path) -> str:
    found = _child(element, *path)
    return (found.text or "").strip() if found is not None else ""


def _date(element) -> date | None:
    value = _text(element, "Dt") or _text(element, "DtTm")[:10]
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def parse(data: bytes) -> ParsedStatement:
    try:
        root = SafeET.fromstring(data)
    except Exception as exc:  # defusedxml raises its own errors for DTDs/entities
        raise StatementError(f"Not a readable camt.053 XML file ({type(exc).__name__}).") from None

    body = _child(root, "BkToCstmrStmt")
    if body is None:
        raise StatementError("XML file is not a camt.053 bank statement (no BkToCstmrStmt).")

    statements = _children(body, "Stmt")
    if not statements:
        raise StatementError("camt.053 file contains no statement.")

    parsed = ParsedStatement(format="camt.053", iban=None, opening_balance=None)
    for statement in statements:
        parsed.iban = parsed.iban or _text(statement, "Acct", "Id", "IBAN") or None

        for balance in _children(statement, "Bal"):
            if _text(balance, "Tp", "CdOrPrtry", "Cd") in ("OPBD", "PRCD") and parsed.opening_balance is None:
                amount = Decimal(_text(balance, "Amt") or "0")
                parsed.opening_balance = -amount if _text(balance, "CdtDbtInd") == "DBIT" else amount

        for entry in _children(statement, "Ntry"):
            status = _text(entry, "Sts") or _text(entry, "Sts", "Cd")
            if status and status != "BOOK":
                parsed.skip("not booked (pending)")
                continue
            if _text(entry, "RvslInd").lower() == "true":
                parsed.skip("reversal")
                continue

            amount_element = _child(entry, "Amt")
            currency = amount_element.get("Ccy", "EUR") if amount_element is not None else "EUR"
            try:
                amount = Decimal((amount_element.text or "").strip())
            except (InvalidOperation, AttributeError):
                parsed.skip("unreadable amount")
                continue
            credit = _text(entry, "CdtDbtInd") == "CRDT"
            booked_on = _date(_child(entry, "BookgDt")) or _date(_child(entry, "ValDt"))
            if booked_on is None:
                parsed.skip("missing date")
                continue

            details = _child(entry, "NtryDtls", "TxDtls")
            parties = _child(details, "RltdPties")
            # For money out the counterparty is the creditor; for money in, the debtor.
            role = "Dbtr" if credit else "Cdtr"
            counterparty = _text(parties, role, "Nm") or _text(parties, role, "Pty", "Nm")
            remittance = " ".join(
                (u.text or "").strip() for u in _children(_child(details, "RmtInf"), "Ustrd")
            ).strip()
            description = remittance or _text(entry, "AddtlNtryInf")

            parsed.entries.append(
                StatementEntry(
                    booked_on=booked_on,
                    amount=amount if credit else -amount,
                    counterparty=counterparty,
                    description=description,
                    currency=currency,
                )
            )
    return parsed
