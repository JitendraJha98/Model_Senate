from datetime import datetime, timezone

import backend.main as main
from backend.mcp_server import consult_council
from backend.schemas import CouncilRun, CouncilSynthesis, ModelRoute, OrchestrationPlan


def _run() -> CouncilRun:
    now = datetime.now(timezone.utc)
    return CouncilRun(
        id="mcp1", status="completed", orchestration_plan=OrchestrationPlan(query_type="factual"),
        agent_opinions=[], council_critiques=[],
        synthesis=CouncilSynthesis(
            leader_model_id="m0", leader_display_name="M0", status="completed",
            direct_answer="42", consensus_points=["agree"], dissent_points=["a caveat"],
        ),
        confidence_grade="A", created_at=now, completed_at=now, prompt="q",
        selected_models=[], total_latency_ms=1,
    )


async def test_consult_council_returns_agent_friendly_result(monkeypatch):
    monkeypatch.setattr(main, "routes", [
        ModelRoute(id="m0", provider="openrouter", model="x", display_name="M0"),
        ModelRoute(id="m1", provider="openrouter", model="y", display_name="M1"),
    ])

    class FakeCouncil:
        async def run(self, request, **kwargs):
            assert request.prompt == "what is the answer?"
            return _run()

    monkeypatch.setattr(main, "council_service", FakeCouncil())
    result = await consult_council("what is the answer?")
    assert result["answer"] == "42"
    assert result["confidence_grade"] == "A"
    assert result["consensus"] == ["agree"]
    assert result["dissent"] == ["a caveat"]
    assert result["status"] == "completed"


async def test_consult_council_guards_on_too_few_models(monkeypatch):
    monkeypatch.setattr(main, "routes", [
        ModelRoute(id="m0", provider="openrouter", model="x", display_name="M0", missing_key=True),
    ])
    result = await consult_council("q")
    assert "error" in result
