from pathlib import Path

import pytest

import main
from storage import BudgetStore

from analytics.insights import build_facts
from analytics.spending import load_transactions

DATA = Path(__file__).resolve().parents[1] / "data" / "transactions.csv"


@pytest.fixture
def sample_facts():
    return build_facts(load_transactions(DATA))


@pytest.fixture(autouse=True)
def isolated_budget_store(tmp_path):
    """Every test gets an empty database; nothing touches backend/data/narrai.db."""
    store = BudgetStore(tmp_path / "test.db")
    main.app.dependency_overrides[main.budget_store] = lambda: store
    yield store
    main.app.dependency_overrides.pop(main.budget_store, None)
