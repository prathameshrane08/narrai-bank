import os
from pathlib import Path

os.environ.setdefault("NARRAI_WARMUP", "0")  # never call the real model from tests

import pytest
from alembic import command
from alembic.config import Config
from fastapi import Header
from sqlalchemy import MetaData, delete

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
    # Start clean when reusing a Postgres test database: drop whatever tables exist, including ones
    # added by newer migrations, so this never needs updating when the schema grows.
    existing = MetaData()
    existing.reflect(engine)
    existing.drop_all(engine)

    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    session_factory = make_session_factory(engine)
    with session_factory.begin() as session:
        for tenant_id in load_tenants():
            seed_tenant(session, tenant_id)
    return Repository(session_factory)


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    """Rate-limit counters don't carry over between tests (tests of the limits reset them too)."""
    from ratelimit import limiter

    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture(autouse=True)
def isolated_repository(repo):
    """Every test starts with no budgets and talks to the test database."""
    with repo.session_factory.begin() as session:
        session.execute(delete(Budget))
    main.app.dependency_overrides[main.repository] = lambda: repo
    yield repo
    main.app.dependency_overrides.pop(main.repository, None)


@pytest.fixture(autouse=True)
def signed_in_as_demo_customer(isolated_repository):
    """Feature tests act as the demo customer of the bank they name (X-NarrAI-Tenant, default narrai).
    Authentication itself is tested without this shortcut in test_auth.py (see `real_auth`)."""
    from tenants import get_tenant

    def demo_sign_in(x_narrai_tenant: str | None = Header(None)):
        tenant = get_tenant(x_narrai_tenant or "narrai")
        return tenant, isolated_repository.find_customer(tenant.id, "demo-customer")

    main.app.dependency_overrides[main.signed_in_customer] = demo_sign_in
    yield
    main.app.dependency_overrides.pop(main.signed_in_customer, None)


@pytest.fixture
def real_auth():
    """Remove the demo shortcut so a test goes through real session tokens."""
    main.app.dependency_overrides.pop(main.signed_in_customer, None)
