from pathlib import Path

import pytest

from backend.schemas import ChatMessage, ModelRoute, SenateRequest, UsageMetadata
from backend.senate import SenateService, build_review_prompt
from backend.storage import ConversationStore


class FakeAdapter:
    def __init__(self, fail_model: str | None = None):
        self.fail_model = fail_model
        self.calls = []

    async def complete(self, route: ModelRoute, messages: list[ChatMessage]):
        self.calls.append((route, messages))
        if route.id == self.fail_model:
            raise RuntimeError("planned failure")
        return f"{route.display_name} answer", UsageMetadata(total_tokens=12), 5


def routes():
    return [
        ModelRoute(id="m1", provider="openrouter", model="one", display_name="Model One", missing_key=False),
        ModelRoute(id="m2", provider="openrouter", model="two", display_name="Model Two", missing_key=False),
        ModelRoute(id="m3", provider="openrouter", model="three", display_name="Model Three", missing_key=False),
    ]


def test_review_prompt_anonymizes_model_names():
    prompt = build_review_prompt(
        [
            type("Opinion", (), {"model_id": "m1", "display_name": "Secret Model", "content": "Alpha"})(),
            type("Opinion", (), {"model_id": "m2", "display_name": "Other Model", "content": "Beta"})(),
        ]
    )
    assert "Response A" in prompt
    assert "Secret Model" not in prompt
    assert "Other Model" not in prompt


@pytest.mark.asyncio
async def test_pipeline_records_partial_failures(tmp_path: Path):
    fake = FakeAdapter(fail_model="m2")
    service = SenateService(routes(), {"openrouter": fake}, ConversationStore(tmp_path))
    run = await service.run(
        SenateRequest(prompt="Explain compounding", selected_model_ids=["m1", "m2", "m3"], leader_model_id="m1")
    )
    assert run.status == "partial_failed"
    assert len(run.first_opinions) == 3
    assert any(output.status == "failed" for output in run.first_opinions)
    saved = (tmp_path / f"{run.id}.json").read_text(encoding="utf-8")
    assert "sk-" not in saved

