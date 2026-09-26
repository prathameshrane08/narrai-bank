import json
import logging

import pytest
from fastapi.testclient import TestClient

import ai.storyteller as storyteller
import main
import observability
from main import app
from observability import JsonFormatter, record_tokens, registry, track_llm

client = TestClient(app)


def sample(name: str, **labels) -> float:
    return registry.get_sample_value(name, labels) or 0.0


@pytest.fixture
def metrics_token(monkeypatch):
    monkeypatch.setenv("NARRAI_METRICS_TOKEN", "scrape-secret-123")
    return {"Authorization": "Bearer scrape-secret-123"}


def test_metrics_are_off_without_a_token_and_protected_with_one(monkeypatch, metrics_token):
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
    body = client.get("/metrics", headers=metrics_token).text
    assert "narrai_http_requests_total" in body and "narrai_llm_requests_total" in body

    monkeypatch.delenv("NARRAI_METRICS_TOKEN")
    assert client.get("/metrics").status_code == 404


@pytest.mark.usefixtures("real_auth")
def test_requests_are_labelled_by_route_template_never_the_customer_reference(repo, metrics_token):
    key, _ = repo.create_api_key("kestrel", "metrics test")
    client.put("/api/customers/secret-ref-8842", json={"display_name": "x"}, headers={"X-NarrAI-API-Key": key})
    body = client.get("/metrics", headers=metrics_token).text

    assert 'route="/api/customers/{customer_ref}"' in body
    assert "secret-ref-8842" not in body


def test_model_calls_tokens_and_cost(monkeypatch):
    monkeypatch.setenv("NARRAI_LLM_PRICE_IN_PER_1K", "0.10")
    monkeypatch.setenv("NARRAI_LLM_PRICE_OUT_PER_1K", "0.30")
    before = (sample("narrai_llm_requests_total", purpose="test", outcome="ok"),
              sample("narrai_llm_tokens_total", purpose="test", kind="prompt"),
              sample("narrai_llm_estimated_cost_eur_total", purpose="test"))

    with track_llm("test"):
        record_tokens(prompt=2000, completion=500)
    with pytest.raises(RuntimeError), track_llm("test"):
        raise RuntimeError("model down")

    assert sample("narrai_llm_requests_total", purpose="test", outcome="ok") == before[0] + 1
    assert sample("narrai_llm_requests_total", purpose="test", outcome="error") >= 1
    assert sample("narrai_llm_tokens_total", purpose="test", kind="prompt") == before[1] + 2000
    assert sample("narrai_llm_estimated_cost_eur_total", purpose="test") == pytest.approx(before[2] + 0.35)


def test_guardrail_outcomes_are_counted(sample_facts, monkeypatch):
    monkeypatch.setattr(storyteller, "_story_cache", {})
    # One made-up number in "what happened"; the other sections are missing, so they fall back too.
    monkeypatch.setattr(storyteller, "_ask_llm", lambda facts: {"what_happened": "Restaurant spending rose by 999%."})
    before = sample("narrai_guardrail_rejections_total", kind="story", reason="unverified_number")
    template_before = sample("narrai_narration_sentences_total", kind="story", section="why", source="template")

    storyteller.generate_story(sample_facts, use_cache=False)

    assert sample("narrai_guardrail_rejections_total", kind="story", reason="unverified_number") == before + 1
    assert sample("narrai_narration_sentences_total", kind="story", section="why", source="template") == template_before + 1


def test_readiness(monkeypatch):
    import ai.providers as providers

    class Down:
        def ping(self):
            raise ConnectionError("no model")

    monkeypatch.setattr(providers, "get_provider", lambda: Down())
    body = client.get("/api/ready").json()
    assert body == {"status": "ready", "database": "ok", "llm": "unavailable (verified templates in use)"}

    monkeypatch.setitem(main.app.dependency_overrides, main.repository, lambda: _BrokenRepo())
    response = client.get("/api/ready")
    assert response.status_code == 503 and response.json()["database"] == "unavailable"
    assert "db.internal" not in response.text  # connection details stay in the server log


class _BrokenRepo:
    def ping(self):
        raise OSError("connection refused to db.internal:5432 user=narrai")


def test_json_log_lines_carry_request_fields_only():
    record = logging.LogRecord("narrai.request", logging.INFO, __file__, 1, "request", None, None)
    for field, value in {"request_id": "abc", "route": "/api/budgets", "status": 200, "duration_ms": 12.5,
                         "tenant": "kestrel"}.items():
        setattr(record, field, value)
    line = json.loads(JsonFormatter().format(record))
    assert {k: line[k] for k in ("level", "message", "request_id", "route", "status", "tenant")} == {
        "level": "info", "message": "request", "request_id": "abc", "route": "/api/budgets", "status": 200,
        "tenant": "kestrel",
    }


def test_issue_kinds_are_a_small_stable_set():
    assert observability.issue_kind("unverified number 180") == "unverified_number"
    assert observability.issue_kind("wrong direction: says up, facts say down") == "wrong_direction"
    assert observability.issue_kind("missing topic (category or merchant)") == "missing_topic"
    assert observability.issue_kind("something new") == "other"


def test_alert_rules_only_use_metrics_the_app_exports():
    import re
    from pathlib import Path

    import yaml

    rules = yaml.safe_load((Path(__file__).resolve().parents[2] / "deploy" / "prometheus" / "alerts.yml").read_text())
    exported = {metric.name for metric in registry.collect()}
    for group in rules["groups"]:
        for rule in group["rules"]:
            used = set(re.findall(r"narrai_[a-z_]+", rule["expr"]))
            base = {re.sub(r"_(bucket|count|sum|total)$", "", name) for name in used}
            assert base <= exported, (rule["alert"], base - exported)
            assert rule["annotations"]["runbook"].startswith("docs/operations.md#")


def test_published_openapi_matches_the_code():
    """docs/openapi.json is what banks integrate against; regenerate with `python -m manage openapi`."""
    from manage import OPENAPI_FILE

    assert json.loads(OPENAPI_FILE.read_text()) == json.loads(json.dumps(app.openapi()))
