from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

import auth
from main import app
from models import LaunchCode

client = TestClient(app)
pytestmark = pytest.mark.usefixtures("real_auth")
WEBAPP = {"X-NarrAI-Client-Secret": "webapp-secret-for-tests-0123456789"}


@pytest.fixture(autouse=True)
def webapp_secret(monkeypatch):
    monkeypatch.setenv("NARRAI_WEBAPP_SECRET", WEBAPP["X-NarrAI-Client-Secret"])


@pytest.fixture
def bank(repo):
    key, _ = repo.create_api_key("kestrel", "launch tests")
    return {"X-NarrAI-API-Key": key}


def launch(bank, ref="demo-family"):
    response = client.post("/api/launch-codes", json={"customer_ref": ref}, headers=bank)
    assert response.status_code == 200, response.text
    url = urlparse(response.json()["launch_url"])
    return url, parse_qs(url.query)["code"][0]


def exchange(code, headers=WEBAPP):
    return client.post("/api/launch-codes/exchange", json={"code": code}, headers=headers)


def test_launch_opens_a_session_for_that_customer_once(bank, repo):
    url, code = launch(bank)
    assert (url.scheme, url.netloc, url.path) == ("http", "localhost:3000", "/launch")  # the bank's app_url

    first = exchange(code)
    assert first.status_code == 200
    body = first.json()
    assert body["tenant"] == "kestrel" and body["customer"]["name"] == "Demo · Family"
    claims = auth.verify_session(body["token"])
    assert repo.customer_by_id("kestrel", claims["sub"]).external_ref == "demo-family"

    replay = exchange(code)
    assert replay.status_code == 401 and "already used" in replay.json()["detail"]


def test_expired_codes_do_not_work(bank, repo):
    _, code = launch(bank)
    with repo.session_factory.begin() as session:
        session.execute(update(LaunchCode).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    assert exchange(code).status_code == 401


def test_exchange_requires_the_web_app_secret(bank, monkeypatch):
    _, code = launch(bank)
    assert exchange(code, headers={}).status_code == 401
    assert exchange(code, headers={"X-NarrAI-Client-Secret": "guess"}).status_code == 401
    assert exchange(code).status_code == 200  # failed attempts didn't burn the code

    monkeypatch.delenv("NARRAI_WEBAPP_SECRET")
    _, other = launch(bank)
    assert exchange(other).status_code == 404  # exchange is off unless a web app is configured


def test_codes_are_stored_hashed_and_unguessable(bank, repo):
    _, code = launch(bank)
    with repo.session_factory() as session:
        stored = session.scalars(select(LaunchCode.code_hash)).all()
    assert code not in stored and len(code) >= 40
    assert exchange("x" * 43).status_code == 401


def test_bank_can_only_launch_its_own_customers(bank):
    assert client.post("/api/launch-codes", json={"customer_ref": "nobody"}, headers=bank).status_code == 404
    assert client.post("/api/launch-codes", json={"customer_ref": "demo-family"}).status_code == 401


def test_bank_without_a_web_app_url_cannot_launch(repo, monkeypatch):
    from tenants import load_tenants

    monkeypatch.setattr(load_tenants()["aurelia"], "app_url", None)
    key, _ = repo.create_api_key("aurelia", "no app")
    response = client.post("/api/launch-codes", json={"customer_ref": "demo-family"}, headers={"X-NarrAI-API-Key": key})
    assert response.status_code == 409


def test_launch_is_audited(bank, repo):
    _, code = launch(bank)
    exchange(code)
    customer = repo.find_customer("kestrel", "demo-family")
    actions = [e["action"] for e in repo.audit_events("kestrel", customer.id)]
    assert actions[:2] == ["session.created", "launch.created"]


def test_app_url_must_be_https_or_localhost():
    from pydantic import ValidationError

    from tenants import Tenant, load_tenants

    base = load_tenants()["kestrel"].model_dump()
    Tenant.model_validate({**base, "app_url": "https://insights.kestrel.example"})
    for bad in ("http://insights.kestrel.example", "https://evil.example/path?x=1", "javascript:alert(1)"):
        with pytest.raises(ValidationError):
            Tenant.model_validate({**base, "app_url": bad})
