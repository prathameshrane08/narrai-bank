"""All database access for the API.

Every method takes the tenant (bank) and, where relevant, the customer, and every
query filters on both. Nothing outside this module writes SQL, so tenant isolation
is enforced in one place and tested in one place.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.orm import sessionmaker

from analytics.spending import prepare_transactions
from models import Account, Budget, Customer, Transaction


@dataclass(frozen=True)
class CustomerRef:
    id: str
    tenant_id: str
    external_ref: str
    display_name: str


class Repository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    # ------------------------------------------------------------------ customers

    def find_customer(self, tenant_id: str, external_ref: str) -> CustomerRef | None:
        with self.session_factory() as session:
            customer = session.scalar(
                select(Customer).where(Customer.tenant_id == tenant_id, Customer.external_ref == external_ref)
            )
        if customer is None:
            return None
        return CustomerRef(customer.id, customer.tenant_id, customer.external_ref, customer.display_name)

    # ------------------------------------------------------------------ money

    def transactions(self, customer: CustomerRef) -> pd.DataFrame:
        """The customer's transactions in the shape the analytics expect."""
        query = (
            select(Transaction.booked_on, Transaction.merchant, Transaction.category, Transaction.amount)
            .join(Account, Account.id == Transaction.account_id)
            .where(
                Transaction.tenant_id == customer.tenant_id,
                Account.tenant_id == customer.tenant_id,
                Account.customer_id == customer.id,
            )
            .order_by(Transaction.booked_on, Transaction.id)
        )
        with self.session_factory() as session:
            rows = session.execute(query).all()

        frame = pd.DataFrame(rows, columns=["date", "merchant", "category", "amount"])
        frame["amount"] = frame["amount"].astype(float)
        return prepare_transactions(frame)

    def opening_balance(self, customer: CustomerRef) -> float:
        with self.session_factory() as session:
            total = session.scalar(
                select(func.coalesce(func.sum(Account.opening_balance), 0)).where(
                    Account.tenant_id == customer.tenant_id, Account.customer_id == customer.id
                )
            )
        return float(total)

    # ------------------------------------------------------------------ budgets

    def budgets(self, customer: CustomerRef) -> dict[str, float]:
        with self.session_factory() as session:
            rows = session.execute(
                select(Budget.category, Budget.amount)
                .where(Budget.tenant_id == customer.tenant_id, Budget.customer_id == customer.id)
                .order_by(Budget.category)
            ).all()
        return {category: float(amount) for category, amount in rows}

    def set_budget(self, customer: CustomerRef, category: str, amount: float) -> None:
        value = Decimal(str(round(amount, 2)))
        with self.session_factory.begin() as session:
            # Never trust the pairing: the customer must belong to this tenant before we write for them.
            owner = session.get(Customer, customer.id)
            if owner is None or owner.tenant_id != customer.tenant_id:
                raise PermissionError("customer does not belong to this tenant")
            budget = session.get(Budget, (customer.id, category))
            if budget is None:
                session.add(Budget(customer_id=customer.id, tenant_id=customer.tenant_id, category=category, amount=value))
            else:
                budget.amount = value
                budget.updated_at = datetime.now(timezone.utc)

    def delete_budget(self, customer: CustomerRef, category: str) -> bool:
        with self.session_factory.begin() as session:
            result = session.execute(
                delete(Budget).where(
                    Budget.tenant_id == customer.tenant_id,
                    Budget.customer_id == customer.id,
                    Budget.category == category,
                )
            )
        return result.rowcount > 0
