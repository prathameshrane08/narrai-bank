"""Alembic environment: uses DATABASE_URL (database.py) and the models' metadata."""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make backend modules importable

from database import database_url, make_engine  # noqa: E402
from models import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    # Tests and tools may pass a URL explicitly; otherwise use the app's configuration.
    return config.get_main_option("sqlalchemy.url") or database_url()


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(_url())
    with engine.connect() as connection:
        # Batch mode lets SQLite apply ALTERs by rebuilding tables; Postgres ignores it.
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
