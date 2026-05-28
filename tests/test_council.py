from pathlib import Path

import pytest

from backend.council import CouncilService
from backend.schemas import ChatMessage, CouncilRequest, ModelRoute, UsageMetadata
from backend.storage import ConversationStore


class FakeAdapter:
    async def complete(self, route: ModelRoute, messages: list[ChatMessage]):
        system = messages[0].content
        if "orchestration agent" in system:
            return (
                '{"query_type":"analytical","is_multi_part":false,"sub_questions":[],'
                '"role_assignments":{"m1":"Independent Expert","m2":"Devil\'s Advocate"},'
                '"tool_assignments":{"m1":[],"m2":[]},"decomposition_rationale":"single question"}',
                UsageMetadata(total_tokens=10),
                5,
            )
        if "critique agent" in system:
            return (
                '{"scores":{"accuracy":0.8,"logic":0.8,"completeness":0.8,"calibration":0.8},'
                '"strengths":["clear"],"weaknesses":[],"flags":[]}',
                UsageMetadata(total_tokens=10),
                5,
            )
        if "elected Model Council leader" in system:
            return (
                '{"direct_answer":"Final answer","consensus":["agreement"],"dissent":[],"unresolved":[],'
                '"confidence_grade":"A","provenance":{}}',
                UsageMetadata(total_tokens=10),
                5,
            )
        if "validate Model Council" in system:
            return '{"status":"approved","issues":[],"addendum":null}', UsageMetadata(total_tokens=10), 5
        return (
            '{"answer":"Opinion","confidence":0.75,"key_claims":["claim"],"assumptions":[],"uncertainties":[]}',
            UsageMetadata(total_tokens=10),
            5,
        )


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
    assert run.synthesis and run.synthesis.direct_answer == "Final answer"
    assert (tmp_path / f"{run.id}.json").exists()
