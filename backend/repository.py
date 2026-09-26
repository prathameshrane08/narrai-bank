"""All database access for the API.

Every method takes the tenant (bank) and, where relevant, the customer, and every
query filters on both. Nothing outside this module writes SQL, so tenant isolation
is enforced in one place and tested in one place.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd
from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import sessionmaker

from analytics.spending import prepare_transactions
from auth import hash_api_key, new_api_key
from models import Account, ApiKey, Budget, Customer, Transaction


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

    def customer_by_id(self, tenant_id: str, customer_id: str) -> CustomerRef | None:
        with self.session_factory() as session:
            customer = session.get(Customer, customer_id)
        if customer is None or customer.tenant_id != tenant_id:
            return None
        return CustomerRef(customer.id, customer.tenant_id, customer.external_ref, customer.display_name)

    def demo_customers(self, tenant_id: str) -> list[CustomerRef]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(Customer)
                .where(Customer.tenant_id == tenant_id, Customer.external_ref.like("demo-%"))
                .order_by(Customer.display_name)
            ).all()
        return [CustomerRef(c.id, c.tenant_id, c.external_ref, c.display_name) for c in rows]

    # ------------------------------------------------------------------ bank API keys

    def create_api_key(self, tenant_id: str, name: str) -> tuple[str, str]:
        """Returns (full key, prefix). The full key is not stored and cannot be shown again."""
        key, prefix, key_hash = new_api_key()
        with self.session_factory.begin() as session:
            session.add(ApiKey(tenant_id=tenant_id, name=name, prefix=prefix, key_hash=key_hash))
        return key, prefix

    def tenant_for_api_key(self, key: str) -> str | None:
        """The bank an active key belongs to (and records its use), or None."""
        with self.session_factory.begin() as session:
            api_key = session.scalar(
                select(ApiKey).where(ApiKey.key_hash == hash_api_key(key), ApiKey.revoked_at.is_(None))
            )
            if api_key is None:
                return None
            api_key.last_used_at = datetime.now(timezone.utc)
            return api_key.tenant_id

    def list_api_keys(self, tenant_id: str) -> list[dict]:
        with self.session_factory() as session:
            keys = session.scalars(
                select(ApiKey).where(ApiKey.tenant_id == tenant_id).order_by(ApiKey.created_at)
            ).all()
        return [
            {"prefix": k.prefix, "name": k.name, "created_at": k.created_at, "last_used_at": k.last_used_at,
             "revoked": k.revoked_at is not None}
            for k in keys
        ]

    def revoke_api_key(self, tenant_id: str, prefix: str) -> bool:
        with self.session_factory.begin() as session:
            api_key = session.scalar(
                select(ApiKey).where(
                    ApiKey.tenant_id == tenant_id, ApiKey.prefix == prefix, ApiKey.revoked_at.is_(None)
                )
            )
            if api_key is None:
                return False
            api_key.revoked_at = datetime.now(timezone.utc)
            return True

    def ensure_customer(self, tenant_id: str, external_ref: str, display_name: str) -> tuple[CustomerRef, bool]:
        """Create the customer if the bank hasn't provisioned it yet. Returns (customer, created)."""
        existing = self.find_customer(tenant_id, external_ref)
        if existing:
            return existing, False
        with self.session_factory.begin() as session:
            customer = Customer(tenant_id=tenant_id, external_ref=external_ref, display_name=display_name)
            session.add(customer)
            session.flush()
            ref = CustomerRef(customer.id, tenant_id, external_ref, display_name)
        return ref, True

    def import_entries(
        self,
        customer: CustomerRef,
        iban_hash: str | None,
        iban_masked: str,
        opening_balance: Decimal | None,
        rows: list[dict],
    ) -> tuple[int, int, str]:
        """Store categorised statement rows on the matching account.
        Returns (imported, duplicates, masked name of the account actually used)."""
        with self.session_factory.begin() as session:
            owner = session.get(Customer, customer.id)
            if owner is None or owner.tenant_id != customer.tenant_id:
                raise PermissionError("customer does not belong to this tenant")

            accounts = select(Account).where(Account.tenant_id == customer.tenant_id, Account.customer_id == customer.id)
            account = None
            if iban_hash:
                account = session.scalar(accounts.where(Account.iban_hash == iban_hash))
            if account is None and not iban_hash:
                account = session.scalar(accounts.order_by(Account.name))  # CSV exports carry no IBAN
            if account is None:
                account = Account(
                    tenant_id=customer.tenant_id,
                    customer_id=customer.id,
                    name="Current account",
                    iban_masked=iban_masked,
                    iban_hash=iban_hash,
                    opening_balance=opening_balance or Decimal("0.00"),
                )
                session.add(account)
                session.flush()

            # 1) Exact re-import of the same file: identical fingerprints.
            fingerprints = [row["fingerprint"] for row in rows]
            known = set(
                session.scalars(
                    select(Transaction.fingerprint).where(
                        Transaction.account_id == account.id, Transaction.fingerprint.in_(fingerprints)
                    )
                ).all()
            ) if fingerprints else set()

            # 2) The same booking arriving in another format (camt.053 vs MT940 vs CSV) words the purpose
            #    differently, so also match on date, amount, direction and category, counting occurrences:
            #    two identical coffees are only duplicates if the account already has two.
            existing = Counter()
            if rows:
                dates = [row["booked_on"] for row in rows]
                for booked_on, amount, direction, category in session.execute(
                    select(Transaction.booked_on, Transaction.amount, Transaction.direction, Transaction.category)
                    .where(Transaction.account_id == account.id,
                           Transaction.booked_on >= min(dates), Transaction.booked_on <= max(dates))
                ):
                    existing[(booked_on, Decimal(amount), direction, category)] += 1

            new_rows = []
            for row in rows:
                key = (row["booked_on"], Decimal(row["amount"]), row["direction"], row["category"])
                if row["fingerprint"] in known:
                    existing[key] -= 1  # consumes its own match
                    continue
                if existing[key] > 0:
                    existing[key] -= 1
                    continue
                new_rows.append({**row, "tenant_id": customer.tenant_id, "account_id": account.id})
            if new_rows:
                session.execute(insert(Transaction), new_rows)
            account_label = account.iban_masked
        return len(new_rows), len(rows) - len(new_rows), account_label

    # ------------------------------------------------------------------ money

    def transactions(self, customer: CustomerRef) -> pd.DataFrame:
        """The customer's transactions in the shape the analytics expect."""
        query = (
            select(Transaction.booked_on, Transaction.merchant, Transaction.category, Transaction.amount,
                   Transaction.direction)
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

        frame = pd.DataFrame(rows, columns=["date", "merchant", "category", "amount", "direction"])
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
