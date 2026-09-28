from database import DEFAULT_URL, database_url


def test_default_is_local_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert database_url() == DEFAULT_URL


def test_hosted_postgres_urls_get_the_psycopg_driver(monkeypatch):
    for given in ("postgres://u:p@db.example/narrai", "postgresql://u:p@db.example/narrai"):
        monkeypatch.setenv("DATABASE_URL", given + "?sslmode=require")
        assert database_url() == "postgresql+psycopg://u:p@db.example/narrai?sslmode=require"


def test_explicit_driver_is_kept(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db.example/narrai")
    assert database_url() == "postgresql+psycopg://u:p@db.example/narrai"
