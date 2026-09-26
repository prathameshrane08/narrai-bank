from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

import auth
import main
from main import app

client = TestClient(app)
pytestmark = pytest.mark.usefixtures("real_auth")  # no shortcuts: real session tokens only


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def session_for(repo, tenant_id: str, ref: str = "demo-customer") -> str:
    customer = repo.find_customer(tenant_id, ref)
    token, _ = auth.issue_session(customer.tenant_id, customer.id)
    return token


def test_customer_endpoints_require_a_session():
    for method, path in [("get", "/api/months"), ("get", "/api/dashboard"), ("get", "/api/budgets"),
                         ("post", "/api/chat"), ("get", "/api/story")]:
        response = getattr(client, method)(path, **({"json": {"question": "hi"}} if method == "post" else {}))
        assert response.status_code == 401, path
        assert response.headers["www-authenticate"] == "Bearer"


def test_public_endpoints_stay_open():
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/tenant", headers={"X-NarrAI-Tenant": "kestrel"}).status_code == 200


def test_valid_session_reaches_that_customers_data(repo):
    body = client.get("/api/dashboard?month=2026-08", headers=bearer(session_for(repo, "narrai"))).json()
    assert body["account"]["balance"] == 14423.8


def test_the_bank_comes_from_the_token_not_a_header(repo):
    token = session_for(repo, "narrai")
    response = client.get("/api/budgets", headers={**bearer(token), "X-NarrAI-Tenant": "kestrel"})
    assert response.status_code == 403


def test_another_banks_session_sees_its_own_customer_only(repo):
    repo.set_budget(repo.find_customer("narrai", "demo-customer"), "Restaurant", 50)

    kestrel = client.get("/api/budgets", headers=bearer(session_for(repo, "kestrel"))).json()
    narrai = client.get("/api/budgets", headers=bearer(session_for(repo, "narrai"))).json()
    assert kestrel["budgets"] == []
    assert [b["category"] for b in narrai["budgets"]] == ["Restaurant"]


def test_forged_expired_and_wrongly_signed_tokens_are_rejected(repo):
    customer = repo.find_customer("narrai", "demo-customer")
    now = datetime.now(timezone.utc)
    base = {"iss": "narrai", "sub": customer.id, "tenant": "narrai", "iat": now, "jti": "x"}

    expired = jwt.encode({**base, "exp": now - timedelta(minutes=1)}, auth._secret(), algorithm="HS256")
    wrong_key = jwt.encode({**base, "exp": now + timedelta(minutes=5)}, "x" * 48, algorithm="HS256")
    unsigned = jwt.encode({**base, "exp": now + timedelta(minutes=5)}, None, algorithm="none")
    other_bank = jwt.encode({**base, "tenant": "kestrel", "exp": now + timedelta(minutes=5)},
                            auth._secret(), algorithm="HS256")  # narrai customer id claimed for kestrel

    for token in (expired, wrong_key, unsigned, other_bank, "not-a-token"):
        assert client.get("/api/months", headers=bearer(token)).status_code == 401


def test_bank_api_key_flow(repo):
    key, prefix = repo.create_api_key("kestrel", "test backend")
    assert key.startswith("nk_") and prefix == key[:12]

    response = client.post("/api/sessions", json={"customer_ref": "demo-family"}, headers={"X-NarrAI-API-Key": key})
    assert response.status_code == 200
    session = response.json()
    assert session["customer"]["name"] == "Demo · Family"

    months = client.get("/api/months", headers=bearer(session["token"]))
    assert months.status_code == 200 and months.json()["latest"] == "2026-08"

    # A Kestrel key only ever opens sessions for Kestrel's own customers.
    claims = auth.verify_session(session["token"])
    assert claims["tenant"] == "kestrel"
    assert repo.customer_by_id("kestrel", claims["sub"]).external_ref == "demo-family"
    assert repo.customer_by_id("narrai", claims["sub"]) is None
    unknown = client.post("/api/sessions", json={"customer_ref": "someone-at-another-bank"},
                          headers={"X-NarrAI-API-Key": key})
    assert unknown.status_code == 404

    assert repo.revoke_api_key("kestrel", prefix) is True
    revoked = client.post("/api/sessions", json={"customer_ref": "demo-family"}, headers={"X-NarrAI-API-Key": key})
    assert revoked.status_code == 401


def test_api_key_is_stored_only_as_a_hash(repo):
    from sqlalchemy import select
    from models import ApiKey

    key, prefix = repo.create_api_key("aurelia", "hash check")
    with repo.session_factory() as session:
        stored = session.scalar(select(ApiKey).where(ApiKey.prefix == prefix))
    assert stored.key_hash == auth.hash_api_key(key)
    assert key not in (stored.key_hash, stored.prefix, stored.name)


def test_sessions_need_a_valid_key():
    assert client.post("/api/sessions", json={"customer_ref": "demo-customer"}).status_code == 401
    bad = client.post("/api/sessions", json={"customer_ref": "demo-customer"}, headers={"X-NarrAI-API-Key": "nk_nope"})
    assert bad.status_code == 401


def test_demo_sign_in_is_off_by_default():
    assert main.DEMO_MODE is False
    assert client.get("/api/demo/customers").status_code == 404
    assert client.post("/api/demo/sessions", json={"customer_ref": "demo-customer"}).status_code == 404
    assert client.get("/api/tenants").json()["tenants"] == []  # client list is confidential


def test_demo_sign_in_only_for_demo_customers(monkeypatch):
    monkeypatch.setattr(main, "DEMO_MODE", True)
    customers = client.get("/api/demo/customers", headers={"X-NarrAI-Tenant": "aurelia"}).json()["customers"]
    assert {c["ref"] for c in customers} == {"demo-customer", "demo-family", "demo-student", "demo-young-professional"}

    ok = client.post("/api/demo/sessions", json={"customer_ref": "demo-student"}, headers={"X-NarrAI-Tenant": "aurelia"})
    assert auth.verify_session(ok.json()["token"])["tenant"] == "aurelia"

    assert client.post("/api/demo/sessions", json={"customer_ref": "real-customer-42"}).status_code == 422
