from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import backend.main as main
from backend.schemas import CouncilRun, CouncilSynthesis, ModelRoute, OrchestrationPlan


def _run() -> CouncilRun:
    now = datetime.now(timezone.utc)
    return CouncilRun(
        id="r", status="completed", orchestration_plan=OrchestrationPlan(query_type="factual"),
        agent_opinions=[], council_critiques=[],
        synthesis=CouncilSynthesis(leader_model_id="m0", leader_display_name="M0",
                                   status="completed", direct_answer="ok"),
        created_at=now, completed_at=now, prompt="q", selected_models=[], total_latency_ms=1,
    )


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "routes", [
        ModelRoute(id="m0", provider="openrouter", model="x", display_name="M0"),
        ModelRoute(id="m1", provider="openrouter", model="y", display_name="M1"),
    ])

    class FakeCouncil:
        async def run(self, request, **kwargs):
            return _run()

    monkeypatch.setattr(main, "council_service", FakeCouncil())
    return TestClient(main.app)


def _post(client):
    return client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "q"}]})


def test_open_when_no_token_configured(client, monkeypatch):
    monkeypatch.setattr(main.settings, "api_auth_token", None)
    assert _post(client).status_code == 200


def test_rejects_missing_and_wrong_token(client, monkeypatch):
    monkeypatch.setattr(main.settings, "api_auth_token", "secret")
    assert _post(client).status_code == 401
    resp = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer wrong"},
        json={"messages": [{"role": "user", "content": "q"}]},
    )
    assert resp.status_code == 401


def test_accepts_correct_token(client, monkeypatch):
    monkeypatch.setattr(main.settings, "api_auth_token", "secret")
    resp = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer secret"},
        json={"messages": [{"role": "user", "content": "q"}]},
    )
    assert resp.status_code == 200
