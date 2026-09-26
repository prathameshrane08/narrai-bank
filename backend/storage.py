"""Persistent customer settings (currently: budgets).

SQLite keeps the prototype dependency-free; every row is scoped by tenant and
customer so the same schema carries over to Postgres in production.
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent / "data" / "narrai.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS budgets (
    tenant_id   TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    category    TEXT NOT NULL,
    amount      REAL NOT NULL CHECK (amount > 0),
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (tenant_id, customer_id, category)
);
"""


class BudgetStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("NARRAI_DB_PATH", DEFAULT_DB_PATH))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def list(self, tenant_id: str, customer_id: str) -> dict[str, float]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT category, amount FROM budgets WHERE tenant_id = ? AND customer_id = ? ORDER BY category",
                (tenant_id, customer_id),
            ).fetchall()
        return {row["category"]: row["amount"] for row in rows}

    def set(self, tenant_id: str, customer_id: str, category: str, amount: float) -> None:
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO budgets (tenant_id, customer_id, category, amount, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (tenant_id, customer_id, category)
                DO UPDATE SET amount = excluded.amount, updated_at = excluded.updated_at
                """,
                (tenant_id, customer_id, category, round(amount, 2), datetime.now(timezone.utc).isoformat()),
            )

    def delete(self, tenant_id: str, customer_id: str, category: str) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                "DELETE FROM budgets WHERE tenant_id = ? AND customer_id = ? AND category = ?",
                (tenant_id, customer_id, category),
            )
        return cursor.rowcount > 0
