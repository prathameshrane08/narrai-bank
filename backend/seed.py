"""Load demo customers into the database, for every bank (tenant).

    python -m seed              # add demo data for banks that don't have it yet
    python -m seed --reset      # delete and re-create all demo customers

Each bank gets the same demo customers so a pitch shows identical numbers in every brand:
  demo-customer            the hand-made sample account (backend/data/transactions.csv)
  demo-young-professional  synthetic 12-month persona (seeded, reproducible)
  demo-family              synthetic 12-month persona
  demo-student             synthetic 12-month persona
"""

import argparse
from decimal import Decimal
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from analytics.synthetic import generate_transactions
from database import make_engine, make_session_factory
from models import Account, Customer, Transaction
from tenants import load_tenants

SAMPLE_CSV = Path(__file__).parent / "data" / "transactions.csv"

DEMO_CUSTOMERS = [
    # (external ref, display name, opening balance, source)
    ("demo-customer", "Demo Customer", Decimal("1840.00"), "sample"),
    ("demo-young-professional", "Demo · Young professional", Decimal("2500.00"), "young_professional"),
    ("demo-family", "Demo · Family", Decimal("6000.00"), "family"),
    ("demo-student", "Demo · Student", Decimal("400.00"), "student"),
]


def _rows(source: str) -> pd.DataFrame:
    if source == "sample":
        return pd.read_csv(SAMPLE_CSV)
    return generate_transactions(source, seed=1)


def seed_tenant(session: Session, tenant_id: str, reset: bool = False) -> int:
    """Create the tenant's demo customers; returns how many were created."""
    refs = [ref for ref, *_ in DEMO_CUSTOMERS]
    if reset:
        session.execute(delete(Customer).where(Customer.tenant_id == tenant_id, Customer.external_ref.in_(refs)))

    existing = set(
        session.scalars(select(Customer.external_ref).where(Customer.tenant_id == tenant_id)).all()
    )
    created = 0
    for ref, name, opening_balance, source in DEMO_CUSTOMERS:
        if ref in existing:
            continue
        customer = Customer(tenant_id=tenant_id, external_ref=ref, display_name=name)
        session.add(customer)
        session.flush()
        account = Account(
            tenant_id=tenant_id,
            customer_id=customer.id,
            name="Current account",
            iban_masked="DE•• •••• •••• •••• •••• 00",
            opening_balance=opening_balance,
        )
        session.add(account)
        session.flush()

        frame = _rows(source)
        session.execute(
            insert(Transaction),
            [
                {
                    "tenant_id": tenant_id,
                    "account_id": account.id,
                    "booked_on": pd.Timestamp(row.date).date(),
                    "merchant": row.merchant,
                    "category": row.category,
                    "amount": Decimal(str(round(float(row.amount), 2))),
                    "direction": "in" if row.category == "Income" else "out",
                }
                for row in frame.itertuples(index=False)
            ],
        )
        created += 1
    return created


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete and re-create the demo customers")
    args = parser.parse_args()

    session_factory = make_session_factory(make_engine())
    with session_factory.begin() as session:
        for tenant_id in load_tenants():
            created = seed_tenant(session, tenant_id, reset=args.reset)
            print(f"{tenant_id}: {created} demo customers created")


if __name__ == "__main__":
    main()
