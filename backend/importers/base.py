"""The shape every statement parser produces, whatever the file format."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


class StatementError(ValueError):
    """The file can't be read as a bank statement (the message is safe to show to the bank)."""


@dataclass(frozen=True)
class StatementEntry:
    booked_on: date
    amount: Decimal  # signed: positive = money in, negative = money out
    counterparty: str  # payee for debits, payer for credits; may be empty
    description: str  # remittance information / purpose; may be empty
    currency: str = "EUR"


@dataclass
class ParsedStatement:
    format: str
    iban: str | None
    opening_balance: Decimal | None
    entries: list[StatementEntry] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)  # reason -> count

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1
