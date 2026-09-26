from pathlib import Path

import pytest

from analytics.insights import build_facts
from analytics.spending import load_transactions

DATA = Path(__file__).resolve().parents[1] / "data" / "transactions.csv"


@pytest.fixture
def sample_facts():
    return build_facts(load_transactions(DATA))
