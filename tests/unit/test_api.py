"""محوّل HTTP (FR-71): العقود الأساسية، بالمسار الحتمي وحده (بلا نموذج ولا شبكة)."""

import pytest

from tests.conftest import needs_data

pytestmark = needs_data
fastapi = pytest.importorskip("fastapi")


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
