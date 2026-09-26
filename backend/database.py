"""Database connection.

Postgres in production (DATABASE_URL=postgresql+psycopg://user:pass@host/db);
a local SQLite file by default so development needs no server.
"""

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

DEFAULT_URL = f"sqlite:///{Path(__file__).parent / 'data' / 'narrai-dev.db'}"


def database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_URL)


def make_engine(url: str | None = None) -> Engine:
    url = url or database_url()
    engine = create_engine(url, pool_pre_ping=True)

    if engine.dialect.name == "sqlite":
        # SQLite ignores foreign keys unless asked; keep its behaviour close to Postgres.
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(engine, expire_on_commit=False)
