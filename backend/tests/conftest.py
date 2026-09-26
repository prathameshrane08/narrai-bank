import os
from pathlib import Path

os.environ.setdefault("NARRAI_WARMUP", "0")  # never call the real model from tests

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, text

import main
from analytics.insights import build_facts
from analytics.spending import load_transactions
from database import make_engine, make_session_factory
from models import Budget
from repository import Repository
from seed import seed_tenant
from tenants import load_tenants

BACKEND = Path(__file__).resolve().parents[1]
DATA = BACKEND / "data" / "transactions.csv"


@pytest.fixture
def sample_facts():
    return build_facts(load_transactions(DATA))


@pytest.fixture(scope="session")
def database_url(tmp_path_factory):
    """SQLite by default; set NARRAI_TEST_DATABASE_URL to run the suite against Postgres (as CI does)."""
    return os.getenv("NARRAI_TEST_DATABASE_URL") or f"sqlite:///{tmp_path_factory.mktemp('db') / 'test.db'}"


@pytest.fixture(scope="session")
def repo(database_url):
    """A fresh database built by the real migrations, with demo data for every bank."""
    engine = make_engine(database_url)
    with engine.begin() as connection:  # start clean (matters when reusing a Postgres test database)
        for table in ("budgets", "transactions", "accounts", "customers", "alembic_version"):
            connection.execute(text(f"DROP TABLE IF EXISTS {table}"))

    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    session_factory = make_session_factory(engine)
    with session_factory.begin() as session:
        for tenant_id in load_tenants():
            seed_tenant(session, tenant_id)
    return Repository(session_factory)


@pytest.fixture(autouse=True)
def isolated_repository(repo):
    """Every test starts with no budgets and talks to the test database."""
    with repo.session_factory.begin() as session:
        session.execute(delete(Budget))
    main.app.dependency_overrides[main.repository] = lambda: repo
    yield repo
    main.app.dependency_overrides.pop(main.repository, None)
