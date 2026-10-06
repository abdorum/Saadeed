"""محوّل HTTP (FR-71): العقود الأساسية، بالمسار الحتمي وحده (بلا نموذج ولا شبكة)."""

import pytest

from tests.conftest import needs_data

pytestmark = needs_data
# استيراد صريح لا importorskip: غياب fastapi عطل في التثبيت يجب أن يُفشل الاختبار (E-018).
import fastapi  # noqa: E402,F401


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from saadeed.adapters.api import app as api

    api.state.llm = None  # لا نداءات حقيقية في الاختبارات
    with TestClient(api.app) as c:
        api.state.llm = None
        yield c


def test_health_and_coverage(client):
    h = client.get("/v1/health").json()
    assert h["ok"] and h["manifest"]["sha256"]
    cov = client.get("/v1/coverage").json()
    ids = {s["id"] for s in cov["connectors"]}
    assert {"quran", "bukhari", "known_weak"} <= ids
    assert any("لا يُولِّد" in p for p in cov["policies"])


def test_quick_review_is_deterministic(client):
    body = {"text": "قال رسول الله ﷺ: «إن الله مع الصابرين».", "mode": "quick"}
    r1 = client.post("/v1/reviews", json=body).json()
    r2 = client.post("/v1/reviews", json=body).json()
    assert r1["findings"][0]["rule_id"] == "BR-22"
    strip = lambda r: [(f["id"], f["rule_id"], f["explanation"]) for f in r["findings"]]  # noqa: E731
    assert strip(r1) == strip(r2)
    assert r1["schema_version"] == "1.1" and r1["mode"] == "quick"


def test_too_long_draft_is_rejected_clearly(client):
    r = client.post("/v1/reviews", json={"text": "كلمة " * 3100, "mode": "quick"})
    assert r.status_code == 422
    assert "أطول من الحد" in r.json()["detail"]


def test_empty_draft_is_rejected(client):
    assert client.post("/v1/reviews", json={"text": "", "mode": "quick"}).status_code == 422


def test_health_lists_providers_without_keys(client):
    h = client.get("/v1/health").json()
    assert set(h["providers"]) == {"gemini", "groq"}
    assert all(set(v) == {"default_model", "server_key"} for v in h["providers"].values())


def test_user_key_choice_none_runs_deterministic(client):
    body = {"text": "قال رسول الله ﷺ: «إن الله مع الصابرين».", "llm": {"provider": "none"}}
    r = client.post("/v1/reviews", json=body)
    assert r.status_code == 200 and r.json()["findings"]


def test_llm_check_never_echoes_the_key(client, monkeypatch):
    from saadeed.adapters.api import app as api
    from saadeed.domain.ports import LLMError

    secret = "AIza-test-not-a-real-key-123"

    class Boom:
        model_id = "gemini:x"

        def generate_json(self, **_):
            raise LLMError(f"401 API key not valid: {secret}")  # مزود يردّد المفتاح في خطئه

    monkeypatch.setattr(api, "build_llm", lambda *a, **k: Boom())  # بلا شبكة
    r = client.post("/v1/llm/check", json={"provider": "gemini", "api_key": secret})
    assert r.status_code == 200 and secret not in r.text
    assert r.json() == {"ok": False, "reason": "مفتاح مزود النموذج غير صالح أو غير مضبوط"}
