import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import auth
from main import app
from ratelimit import RateLimiter

client = TestClient(app)
BACKEND = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.usefixtures("real_auth")


def session_headers(repo, tenant="narrai", ref="demo-customer"):
    customer = repo.find_customer(tenant, ref)
    token, _ = auth.issue_session(customer.tenant_id, customer.id, customer.session_generation)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def bank(repo):
    key, _ = repo.create_api_key("kestrel", "security tests")
    return {"X-NarrAI-API-Key": key}


# ------------------------------------------------------------------ headers


def test_security_headers_and_no_caching(repo):
    response = client.get("/api/months", headers=session_headers(repo))
    headers = response.headers
    assert headers["cache-control"] == "no-store"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert headers["referrer-policy"] == "no-referrer"
    assert len(headers["x-request-id"]) == 32


def test_request_id_is_echoed_only_if_well_formed():
    assert client.get("/api/health", headers={"X-Request-ID": "bank-req-42"}).headers["x-request-id"] == "bank-req-42"
    injected = client.get("/api/health", headers={"X-Request-ID": "x\r\nSet-Cookie: evil=1"}).headers["x-request-id"]
    assert injected != "x\r\nSet-Cookie: evil=1" and "set-cookie" not in client.get("/api/health").headers


# ------------------------------------------------------------------ sessions


def test_sign_out_kills_the_token_immediately(repo):
    headers = session_headers(repo)
    assert client.get("/api/months", headers=headers).status_code == 200
    assert client.post("/api/sessions/current/revoke", headers=headers).status_code == 204
    assert client.get("/api/months", headers=headers).status_code == 401
    assert client.get("/api/months", headers=session_headers(repo)).status_code == 200  # a new sign-in works


def test_bank_can_sign_a_customer_out_everywhere(repo, bank):
    phone, laptop = session_headers(repo, "kestrel"), session_headers(repo, "kestrel")
    assert client.post("/api/customers/demo-customer/sessions/revoke-all", headers=bank).status_code == 204

    assert client.get("/api/months", headers=phone).status_code == 401
    assert client.get("/api/months", headers=laptop).status_code == 401
    # Signing in again straight away works (no clock-resolution gap).
    fresh = client.post("/api/sessions", json={"customer_ref": "demo-customer"}, headers=bank).json()["token"]
    assert client.get("/api/months", headers={"Authorization": f"Bearer {fresh}"}).status_code == 200
    # Other banks' customers are untouched.
    assert client.get("/api/months", headers=session_headers(repo, "narrai")).status_code == 200


# ------------------------------------------------------------------ rate limits


def test_limiter_counts_a_sliding_window():
    limits = RateLimiter({"test": (2, 60)})
    limits.check("test", "a")
    limits.check("test", "a")
    limits.check("test", "b")  # separate key, separate budget
    with pytest.raises(Exception) as blocked:
        limits.check("test", "a")
    assert blocked.value.status_code == 429 and int(blocked.value.headers["Retry-After"]) >= 1


def test_guessing_api_keys_gets_blocked():
    codes = [client.post("/api/sessions", json={"customer_ref": "x"},
                         headers={"X-NarrAI-API-Key": f"nk_guess{i}"}).status_code for i in range(25)]
    assert codes[:20] == [401] * 20
    assert set(codes[20:]) == {429}


def test_chat_is_limited_per_customer(repo, monkeypatch):
    import ai.assistant as assistant

    monkeypatch.setattr(assistant, "get_provider", lambda: (_ for _ in ()).throw(ConnectionError("offline")))
    headers = session_headers(repo)
    codes = [client.post("/api/chat", json={"question": "How much did I spend?"}, headers=headers).status_code
             for _ in range(22)]
    assert codes.count(200) == 20 and codes[-1] == 429


# ------------------------------------------------------------------ audit log


def test_actions_are_audited_without_personal_data(repo, bank):
    client.post("/api/sessions", json={"customer_ref": "demo-family"}, headers=bank)
    headers = session_headers(repo, "kestrel", "demo-family")
    client.put("/api/budgets/Groceries", json={"amount": 600}, headers=headers)
    client.delete("/api/budgets/Groceries", headers=headers)

    events = client.get("/api/audit?customer_ref=demo-family", headers=bank).json()["events"]
    actions = [e["action"] for e in events]
    assert {"session.created", "budget.set", "budget.deleted"} <= set(actions)
    text = json.dumps(events)
    assert "Family" not in text and "600" not in text  # no names, no amounts
    assert all(e["request_id"] for e in events)


def test_audit_log_is_per_bank(repo, bank):
    other, _ = repo.create_api_key("aurelia", "other bank")
    client.post("/api/sessions", json={"customer_ref": "demo-student"}, headers=bank)
    aurelia_events = client.get("/api/audit", headers={"X-NarrAI-API-Key": other}).json()["events"]
    assert all(e["actor"] != f"bank:{bank['X-NarrAI-API-Key'][:12]}" for e in aurelia_events)


# ------------------------------------------------------------------ GDPR


def test_customer_can_download_their_data(repo):
    response = client.get("/api/me/export", headers=session_headers(repo))
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="my-data.json"'
    data = response.json()
    assert data["customer"]["ref"] == "demo-customer"
    sample_rows = len((BACKEND / "data" / "transactions.csv").read_text().strip().splitlines()) - 1
    assert len(data["transactions"]) == sample_rows
    assert {"accounts", "budgets", "activity"} <= set(data)


def test_bank_export_and_erasure(repo, bank):
    provision = client.put("/api/customers/gdpr-1", json={"display_name": "Erasure test"}, headers=bank)
    assert provision.json()["created"] is True
    client.post("/api/customers/gdpr-1/statements",
                content=(BACKEND / "tests" / "fixtures" / "statement.mt940").read_bytes(), headers=bank)
    session = client.post("/api/sessions", json={"customer_ref": "gdpr-1"}, headers=bank).json()["token"]
    customer_headers = {"Authorization": f"Bearer {session}"}
    customer_id = repo.find_customer("kestrel", "gdpr-1").id

    exported = client.get("/api/customers/gdpr-1/export", headers=bank).json()
    assert len(exported["transactions"]) == 5

    erased = client.delete("/api/customers/gdpr-1", headers=bank).json()
    assert erased == {"deleted": True, "removed": {"transactions": 5, "budgets": 0, "accounts": 1}}
    assert repo.find_customer("kestrel", "gdpr-1") is None
    assert client.get("/api/months", headers=customer_headers).status_code == 401  # session dead
    assert client.get("/api/customers/gdpr-1/export", headers=bank).status_code == 404

    # The audit trail keeps the pseudonymous id only, so the erasure itself stays accountable.
    events = repo.audit_events("kestrel", customer_id)
    assert events[0]["action"] == "customer.deleted"
    assert "Erasure test" not in json.dumps(events)


def test_retention_purge(repo):
    from manage import months_before

    assert months_before(date(2026, 9, 26), 24) == date(2024, 9, 1)
    customer = repo.find_customer("aurelia", "demo-family")
    before = len(repo.transactions(customer))
    removed = repo.purge("aurelia", date(2026, 1, 1))
    after = repo.transactions(customer)
    assert removed["transactions"] > 0
    assert len(after) < before and after["date"].min().date() >= date(2026, 1, 1)
    # Other banks keep their data.
    assert repo.transactions(repo.find_customer("narrai", "demo-family"))["date"].min().date() < date(2026, 1, 1)
