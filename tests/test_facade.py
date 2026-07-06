from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import backend.main as main
from backend.facade import OAIMessage, council_answer, messages_to_prompt
from backend.schemas import (
    CouncilRun,
    CouncilSynthesis,
    ModelRoute,
    OrchestrationPlan,
    ReintegrationOutput,
)


def _canned_run(answer: str = "Paris") -> CouncilRun:
    now = datetime.now(timezone.utc)
    return CouncilRun(
        id="run123",
        status="completed",
        orchestration_plan=OrchestrationPlan(query_type="factual"),
        agent_opinions=[],
        council_critiques=[],
        synthesis=CouncilSynthesis(
            leader_model_id="m1", leader_display_name="M1", status="completed", direct_answer=answer
        ),
        confidence_grade="A",
        created_at=now,
        completed_at=now,
        prompt="q",
        selected_models=[],
        total_latency_ms=1,
        total_tokens=42,
    )


def test_messages_to_prompt_single_user_and_system():
    prompt, system = messages_to_prompt([
        OAIMessage(role="system", content="be terse"),
        OAIMessage(role="user", content="hi"),
    ])
    assert prompt == "hi"
    assert system == "be terse"


def test_messages_to_prompt_flattens_multi_turn():
    prompt, system = messages_to_prompt([
        OAIMessage(role="user", content="a"),
        OAIMessage(role="assistant", content="b"),
        OAIMessage(role="user", content="c"),
    ])
    assert system is None
    assert prompt == "USER: a\n\nASSISTANT: b\n\nUSER: c"


def test_council_answer_prefers_reintegration():
    run = _canned_run()
    run.reintegration = ReintegrationOutput(status="completed", unified_answer="Unified")
    assert council_answer(run) == "Unified"


def _routes(available: int):
    return [
        ModelRoute(id=f"m{i}", provider="openrouter", model="x", display_name=f"M{i}",
                   missing_key=(i >= available))
        for i in range(2)
    ]


def test_facade_returns_openai_shaped_completion(monkeypatch):
    monkeypatch.setattr(main, "routes", _routes(available=2))

    class FakeCouncil:
        async def run(self, request, **kwargs):
            assert request.prompt == "What is the capital of France?"
            assert request.system_context == "be terse"
            return _canned_run("Paris")

    monkeypatch.setattr(main, "council_service", FakeCouncil())
    client = TestClient(main.app)
    resp = client.post("/v1/chat/completions", json={
        "model": "council",
        "messages": [
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "What is the capital of France?"},
        ],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "chat.completion"
    assert data["choices"][0]["message"]["content"] == "Paris"
    assert data["choices"][0]["finish_reason"] == "stop"
    assert data["usage"]["total_tokens"] == 42
    assert data["x_council"] == {"confidence_grade": "A", "run_id": "run123", "status": "completed"}


def test_facade_streams_openai_chunks(monkeypatch):
    monkeypatch.setattr(main, "routes", _routes(available=2))

    class FakeCouncil:
        async def run(self, request, **kwargs):
            return _canned_run("Paris")

    monkeypatch.setattr(main, "council_service", FakeCouncil())
    client = TestClient(main.app)
    resp = client.post("/v1/chat/completions", json={
        "model": "council", "stream": True,
        "messages": [{"role": "user", "content": "q"}],
    })
    assert resp.status_code == 200
    body = resp.text
    assert "chat.completion.chunk" in body
    assert '"content": "Paris"' in body
    assert body.rstrip().endswith("data: [DONE]")


def test_facade_requires_minimum_models(monkeypatch):
    monkeypatch.setattr(main, "routes", _routes(available=1))  # only 1 usable, min is 2

    class FakeCouncil:
        async def run(self, request, **kwargs):  # pragma: no cover - should not be called
            raise AssertionError("council should not run without enough models")

    monkeypatch.setattr(main, "council_service", FakeCouncil())
    client = TestClient(main.app)
    resp = client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "q"}]})
    assert resp.status_code == 400
