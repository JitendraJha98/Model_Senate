from pathlib import Path

import pytest

from backend.council import CouncilService
from backend.schemas import ChatMessage, CouncilRequest, ModelRoute, UsageMetadata
from backend.storage import ConversationStore


ORCHESTRATOR_PLAN = (
    '{"query_type":"analytical","is_multi_part":false,"sub_questions":[],'
    '"role_assignments":{"m1":"Independent Expert","m2":"Devil\'s Advocate"},'
    '"tool_assignments":{"m1":[],"m2":[]},"decomposition_rationale":"single question"}'
)

STAGE1_RESPONSE = (
    "Here is my analysis.\n\n"
    "COUNCIL_OUTPUT:\n"
    '{"answer_summary":"Test answer","confidence":0.75,"confidence_rationale":"moderate certainty",'
    '"key_claims":[{"text":"claim one","verifiable":false,"source":null,"verified":false}],'
    '"uncertainties":["some uncertainty"],"tool_results":[]}'
)

CRITIQUE_RESPONSE = (
    '{"reviews":{"Agent B":{"factual_accuracy_score":0.8,"logical_validity_score":0.8,'
    '"completeness_score":0.8,"calibration_score":0.8,"overall_rank":1,'
    '"strengths":["clear"],"weaknesses":[],"corrective_additions":[]}}}'
)

SYNTHESIS_RESPONSE = (
    '{"direct_answer":"Final answer","consensus_points":["agreement"],'
    '"dissent_points":[],"unresolved_conflicts":[],"confidence_grade":"A",'
    '"confidence_grade_rationale":"high agreement","recommended_next_checks":[],'
    '"provenance_map":{}}'
)

VALIDATION_RESPONSE = (
    '{"verdict":"approved","checks":{"dissents_addressed":true,"confidence_calibrated":true,'
    '"no_hallucinations":true,"answers_original_query":true,"next_checks_actionable":true},'
    '"issues":[],"addendum":null}'
)


class FakeAdapter:
    async def complete(self, route: ModelRoute, messages: list[ChatMessage]):
        system = messages[0].content if messages else ""
        if "orchestration agent" in system:
            return ORCHESTRATOR_PLAN, UsageMetadata(total_tokens=10), 5
        if "critique agent" in system:
            return CRITIQUE_RESPONSE, UsageMetadata(total_tokens=10), 5
        if "elected Synthesizer" in system:
            return SYNTHESIS_RESPONSE, UsageMetadata(total_tokens=10), 5
        if "validate Model Council" in system:
            return VALIDATION_RESPONSE, UsageMetadata(total_tokens=10), 5
        return STAGE1_RESPONSE, UsageMetadata(total_tokens=10), 5


def routes():
    return [
        ModelRoute(id="m1", provider="openrouter", model="one", display_name="Model One", missing_key=False),
        ModelRoute(id="m2", provider="openrouter", model="two", display_name="Model Two", missing_key=False),
    ]


@pytest.mark.asyncio
async def test_council_pipeline_saves_completed_run(tmp_path: Path):
    service = CouncilService(
        routes=routes(),
        adapters={"openrouter": FakeAdapter()},
        store=ConversationStore(tmp_path),
        tool_registry={},
        orchestrator_model_id="m1",
    )

    run = await service.run(CouncilRequest(prompt="Compare options", selected_model_ids=["m1", "m2"]))

    assert run.status == "completed"
    assert run.orchestration_plan.query_type == "analytical"
    assert len(run.agent_opinions) == 2
    assert run.leader_election is not None
    assert run.leader_election.elected_model_id in {"m1", "m2"}
    assert run.synthesis is not None
    assert run.synthesis.direct_answer == "Final answer"
    assert run.synthesis.consensus_points == ["agreement"]
    assert run.validation is not None
    assert run.validation.verdict == "approved"
    assert (tmp_path / f"{run.id}.json").exists()


@pytest.mark.asyncio
async def test_council_pipeline_stage_opinions_structured(tmp_path: Path):
    service = CouncilService(
        routes=routes(),
        adapters={"openrouter": FakeAdapter()},
        store=ConversationStore(tmp_path),
        tool_registry={},
        orchestrator_model_id="m1",
    )

    run = await service.run(CouncilRequest(prompt="Test query", selected_model_ids=["m1", "m2"]))

    for opinion in run.agent_opinions:
        assert opinion.status in {"completed", "parse_failed", "failed"}
        # At least some opinions should have structured output parsed
    assert any(o.structured_output_parsed for o in run.agent_opinions)


MULTI_PART_PLAN = (
    '{"query_type":"multi_part","is_multi_part":true,'
    '"sub_questions":[{"question":"Part one?","query_type":"factual"},'
    '{"question":"Part two?","query_type":"analytical"}],'
    '"role_assignments":{"m1":"Independent Expert","m2":"Devil\'s Advocate"},'
    '"tool_assignments":{"m1":[],"m2":[]},"decomposition_rationale":"two distinct questions"}'
)

REINTEGRATION_RESPONSE = (
    '{"unified_answer":"Combined final answer","contradictions_resolved":[],'
    '"contradictions_unresolved":[],"final_confidence_grade":"B"}'
)


class MultiPartAdapter:
    """Returns a multi-part plan first, then behaves like the single-pipeline FakeAdapter."""

    def __init__(self):
        self._plan_served = False

    async def complete(self, route: ModelRoute, messages: list[ChatMessage]):
        system = messages[0].content if messages else ""
        if "orchestration agent" in system:
            if not self._plan_served:
                self._plan_served = True
                return MULTI_PART_PLAN, UsageMetadata(total_tokens=10), 5
            return ORCHESTRATOR_PLAN, UsageMetadata(total_tokens=10), 5
        if "Re-integration Agent" in system:
            return REINTEGRATION_RESPONSE, UsageMetadata(total_tokens=10), 5
        if "critique agent" in system:
            return CRITIQUE_RESPONSE, UsageMetadata(total_tokens=10), 5
        if "elected Synthesizer" in system:
            return SYNTHESIS_RESPONSE, UsageMetadata(total_tokens=10), 5
        if "validate Model Council" in system:
            return VALIDATION_RESPONSE, UsageMetadata(total_tokens=10), 5
        return STAGE1_RESPONSE, UsageMetadata(total_tokens=10), 5


@pytest.mark.asyncio
async def test_council_multi_part_reintegrates_sub_runs(tmp_path: Path):
    service = CouncilService(
        routes=routes(),
        adapters={"openrouter": MultiPartAdapter()},
        store=ConversationStore(tmp_path),
        tool_registry={},
        orchestrator_model_id="m1",
    )

    run = await service.run(CouncilRequest(prompt="Part one? Part two?", selected_model_ids=["m1", "m2"]))

    assert run.metadata["mode"] == "multi_part"
    assert len(run.sub_runs) == 2
    assert run.reintegration is not None
    assert run.reintegration.unified_answer == "Combined final answer"
    assert run.synthesis is None
    assert (tmp_path / f"{run.id}.json").exists()


@pytest.mark.asyncio
async def test_council_all_stage1_fail_returns_failed_run(tmp_path: Path):
    class AlwaysFailAdapter:
        async def complete(self, route, messages):
            raise RuntimeError("Provider down")

    service = CouncilService(
        routes=routes(),
        adapters={"openrouter": AlwaysFailAdapter()},
        store=ConversationStore(tmp_path),
        tool_registry={},
        orchestrator_model_id="m1",
    )

    run = await service.run(CouncilRequest(prompt="Test", selected_model_ids=["m1", "m2"]))
    assert run.status == "failed"
    assert len(run.errors) > 0
