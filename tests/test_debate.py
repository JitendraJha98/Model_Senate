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
STAGE1 = (
    'Analysis.\n\nCOUNCIL_OUTPUT:\n'
    '{"answer_summary":"first","confidence":0.6,"key_claims":[],"uncertainties":[]}'
)
CRITIQUE = (
    '{"reviews":{"Agent B":{"factual_accuracy_score":0.8,"logical_validity_score":0.8,'
    '"completeness_score":0.8,"calibration_score":0.8,"overall_rank":1,'
    '"strengths":["clear"],"weaknesses":["missed X"],"corrective_additions":["add X"]}}}'
)
SYNTHESIS = (
    '{"direct_answer":"Final","consensus_points":[],"dissent_points":[],'
    '"unresolved_conflicts":[],"confidence_grade":"A","recommended_next_checks":[],"provenance_map":{}}'
)
VALIDATION = (
    '{"verdict":"approved","checks":{"dissents_addressed":true,"confidence_calibrated":true,'
    '"no_hallucinations":true,"answers_original_query":true,"next_checks_actionable":true},'
    '"issues":[],"addendum":null}'
)


def _routes():
    return [
        ModelRoute(id="m1", provider="openrouter", model="one", display_name="Model One"),
        ModelRoute(id="m2", provider="openrouter", model="two", display_name="Model Two"),
    ]


class ConvergingAdapter:
    """Stage-1 gives an opinion; every revision reports changed=false → converge in round 1."""

    def __init__(self):
        self.revision_calls = 0

    async def complete(self, route, messages, *, json_mode: bool = False):
        system = messages[0].content if messages else ""
        if "orchestration agent" in system:
            return ORCHESTRATOR_PLAN, UsageMetadata(total_tokens=10), 5
        if "revising your Model Council opinion" in system:
            self.revision_calls += 1
            return (
                'Reconsidered.\n\nCOUNCIL_OUTPUT:\n'
                '{"answer_summary":"first","confidence":0.7,"key_claims":[],'
                '"uncertainties":[],"changed":false}',
                UsageMetadata(total_tokens=10),
                5,
            )
        if "critique agent" in system:
            return CRITIQUE, UsageMetadata(total_tokens=10), 5
        if "elected Synthesizer" in system:
            return SYNTHESIS, UsageMetadata(total_tokens=10), 5
        if "validate Model Council" in system:
            return VALIDATION, UsageMetadata(total_tokens=10), 5
        return STAGE1, UsageMetadata(total_tokens=10), 5


async def test_debate_disabled_by_default_runs_no_rounds(tmp_path: Path):
    service = CouncilService(
        routes=_routes(),
        adapters={"openrouter": ConvergingAdapter()},
        store=ConversationStore(tmp_path),
        tool_registry={},
        orchestrator_model_id="m1",
    )
    run = await service.run(CouncilRequest(prompt="q", selected_model_ids=["m1", "m2"]))
    assert run.debate_rounds == []


async def test_debate_runs_and_converges_on_self_report(tmp_path: Path):
    adapter = ConvergingAdapter()
    service = CouncilService(
        routes=_routes(),
        adapters={"openrouter": adapter},
        store=ConversationStore(tmp_path),
        tool_registry={},
        orchestrator_model_id="m1",
        debate_enabled=True,
        debate_max_rounds=2,
    )
    run = await service.run(CouncilRequest(prompt="q", selected_model_ids=["m1", "m2"]))

    # One round happened, every model revised, and all reported changed=false → converged.
    assert len(run.debate_rounds) == 1
    assert len(run.debate_rounds[0]) == 2
    assert all(o.revision_round == 1 for o in run.debate_rounds[0])
    assert all(o.changed is False for o in run.debate_rounds[0])
    assert adapter.revision_calls == 2  # 2 models × 1 round
    assert run.status == "completed"


class NeverConvergingAdapter(ConvergingAdapter):
    """Revisions never self-report convergence, so the round cap must stop the loop."""

    async def complete(self, route, messages, *, json_mode: bool = False):
        system = messages[0].content if messages else ""
        if "revising your Model Council opinion" in system:
            self.revision_calls += 1
            return (
                'Still thinking.\n\nCOUNCIL_OUTPUT:\n'
                '{"answer_summary":"changed","confidence":0.7,"key_claims":[],'
                '"uncertainties":[],"changed":true}',
                UsageMetadata(total_tokens=10),
                5,
            )
        return await super().complete(route, messages, json_mode=json_mode)


async def test_debate_respects_max_rounds_cap(tmp_path: Path):
    adapter = NeverConvergingAdapter()
    service = CouncilService(
        routes=_routes(),
        adapters={"openrouter": adapter},
        store=ConversationStore(tmp_path),
        tool_registry={},
        orchestrator_model_id="m1",
        debate_enabled=True,
        debate_max_rounds=2,
    )
    run = await service.run(CouncilRequest(prompt="q", selected_model_ids=["m1", "m2"]))
    assert len(run.debate_rounds) == 2  # capped, never converged
    assert adapter.revision_calls == 4  # 2 models × 2 rounds


async def test_no_election_ablation_uses_heuristic_leader(tmp_path: Path):
    service = CouncilService(
        routes=_routes(),
        adapters={"openrouter": ConvergingAdapter()},
        store=ConversationStore(tmp_path),
        tool_registry={},
        orchestrator_model_id="m1",
        enable_election=False,
    )
    run = await service.run(CouncilRequest(prompt="q", selected_model_ids=["m1", "m2"]))
    assert run.leader_election is not None
    assert "Heuristic leader" in run.leader_election.rationale
