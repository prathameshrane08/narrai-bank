import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import ai.assistant as assistant
from main import app
from tenants import Colours, Tenant, contrast_ratio, load_tenants

client = TestClient(app)


def test_all_shipped_tenants_are_valid_and_include_default():
    tenants = load_tenants()
    assert {"narrai", "kestrel", "aurelia"} <= set(tenants)


def test_contrast_ratio_matches_wcag_reference_values():
    assert contrast_ratio("#ffffff", "#000000") == pytest.approx(21.0)
    assert contrast_ratio("#ffffff", "#ffffff") == pytest.approx(1.0)


def test_unreadable_brand_colours_are_rejected():
    # Pale yellow header with white text: unreadable, so the config must not load.
    with pytest.raises(ValidationError, match="WCAG AA"):
        Colours(brand="#ffe066", brand_dark="#00106e", brand_soft="#fff9db")


def test_logo_must_be_a_local_tenant_asset():
    base = load_tenants()["narrai"].model_dump()
    with pytest.raises(ValidationError, match="logo"):
        Tenant.model_validate({**base, "logo": "https://evil.example/logo.svg"})


def test_tenant_endpoint_uses_header_and_defaults():
    assert client.get("/api/tenant").json()["id"] == "narrai"
    kestrel = client.get("/api/tenant", headers={"X-NarrAI-Tenant": "kestrel"}).json()
    assert kestrel["bank_name"] == "Kestrel Bank"
    assert kestrel["colours"]["brand"] == "#0b6e4f"
    assert client.get("/api/tenant", headers={"X-NarrAI-Tenant": "nope"}).status_code == 404
    assert {"id": "aurelia", "bank_name": "Aurelia Privatbank"} in client.get("/api/tenants").json()["tenants"]


def test_advice_reply_names_the_banks_own_adviser(monkeypatch):
    monkeypatch.setattr(assistant, "get_provider", lambda: (_ for _ in ()).throw(AssertionError("no model call")))
    body = client.post(
        "/api/chat",
        json={"question": "Should I buy crypto?", "month": "2026-08"},
        headers={"X-NarrAI-Tenant": "aurelia"},
    ).json()
    assert body["source"] == "policy"
    assert "your personal Aurelia relationship manager" in body["answer"]


def test_disabled_feature_is_refused(monkeypatch):
    tenant = load_tenants()["kestrel"]
    monkeypatch.setitem(tenant.features, "chat", False)
    response = client.post(
        "/api/chat", json={"question": "How much did I spend?"}, headers={"X-NarrAI-Tenant": "kestrel"}
    )
    assert response.status_code == 403
