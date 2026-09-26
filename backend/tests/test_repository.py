from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from analytics.insights import build_facts
from analytics.spending import load_transactions
from database import make_engine
from models import Base, Budget
from repository import CustomerRef
from main import app

DATA = Path(__file__).resolve().parents[1] / "data" / "transactions.csv"
client = TestClient(app)


def demo(repo, tenant_id):
    return repo.find_customer(tenant_id, "demo-customer")


def test_database_numbers_match_the_original_csv(repo):
    from_db = build_facts(repo.transactions(demo(repo, "narrai")))
    from_csv = build_facts(load_transactions(DATA))
    assert from_db == from_csv


def test_every_bank_has_its_own_demo_customers(repo):
    narrai, kestrel = demo(repo, "narrai"), demo(repo, "kestrel")
    assert narrai.id != kestrel.id
    assert repo.find_customer("narrai", "demo-family") is not None
    assert repo.find_customer("narrai", "no-such-customer") is None


def test_budgets_are_isolated_between_banks(repo):
    repo.set_budget(demo(repo, "narrai"), "Restaurant", 50)

    assert repo.budgets(demo(repo, "narrai")) == {"Restaurant": 50.0}
    assert repo.budgets(demo(repo, "kestrel")) == {}
    assert client.get("/api/budgets", headers={"X-NarrAI-Tenant": "kestrel"}).json()["budgets"] == []


def test_forged_customer_from_another_bank_sees_and_changes_nothing(repo):
    narrai = demo(repo, "narrai")
    repo.set_budget(narrai, "Restaurant", 50)
    # A Kestrel request that somehow carries a NarrAI customer id.
    forged = CustomerRef(id=narrai.id, tenant_id="kestrel", external_ref="x", display_name="x")

    assert repo.transactions(forged).empty
    assert repo.budgets(forged) == {}
    assert repo.opening_balance(forged) == 0.0
    assert repo.delete_budget(forged, "Restaurant") is False
    with pytest.raises(PermissionError):
        repo.set_budget(forged, "Groceries", 10)

    assert repo.budgets(narrai) == {"Restaurant": 50.0}  # untouched


def test_database_rejects_invalid_budgets(repo):
    narrai = demo(repo, "narrai")
    with pytest.raises(IntegrityError):
        with repo.session_factory.begin() as session:
            session.add(Budget(customer_id=narrai.id, tenant_id="narrai", category="Restaurant", amount=-5))


def test_opening_balance_and_personas(repo):
    assert repo.opening_balance(demo(repo, "narrai")) == 1840.0
    family = repo.transactions(repo.find_customer("kestrel", "demo-family"))
    assert "Housing" in set(family["category"]) and len(family) > 300


def test_migrations_match_the_models(database_url):
    """If someone changes models.py without a migration, this fails."""
    with make_engine(database_url).connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == []
