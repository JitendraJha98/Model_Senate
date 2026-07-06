"""Run one configuration on one eval item and return a `Prediction`.

Configurations (the field the Council must beat):
  single:<model_id>                 one completion
  self_consistency:<model_id>:<k>   k completions + majority vote (Wang et al.)
  senate                            SenateService final synthesis
  council                           full CouncilService synthesis
  council_no_debate|_no_critique|_no_election|_no_tools   ablations
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field

from backend.council import CouncilService
from backend.eval.datasets import EvalItem
from backend.eval.scorers import _normalize
from backend.providers import ProviderAdapter
from backend.schemas import ChatMessage, CouncilRequest, ModelRoute, SenateRequest
from backend.senate import SenateService
from backend.storage import ConversationStore
from backend.tools import ToolRegistry
from pydantic import BaseModel

# Council confidence grade → probability, used as the ECE confidence signal.
GRADE_PROB = {"A": 0.9, "B": 0.75, "C": 0.5, "D": 0.3, "F": 0.1}

# Council ablation config name → CouncilService toggle overrides.
_ABLATIONS = {
    "council": {},
    "council_no_debate": {"debate_enabled": False},
    "council_no_critique": {"enable_critique": False},
    "council_no_election": {"enable_election": False},
    "council_no_tools": {"no_tools": True},
}


class Prediction(BaseModel):
    config: str
    item_id: str
    suite: str
    answer: str = ""
    confidence: float | None = None
    grade: str | None = None
    cost_usd: float = 0.0
    latency_s: float = 0.0
    tokens: int = 0
    correct: bool | None = None
    error: str | None = None


@dataclass
class EvalContext:
    routes: list[ModelRoute]
    adapters: dict[str, ProviderAdapter]
    store: ConversationStore
    tool_registry: ToolRegistry
    orchestrator_model_id: str
    council_ids: list[str] = field(default_factory=list)  # models the council convenes
    debate_enabled: bool = True

    def route(self, model_id: str) -> ModelRoute:
        for r in self.routes:
            if r.id == model_id:
                return r
        raise ValueError(f"Unknown model route: {model_id}")

    def council_model_ids(self) -> list[str]:
        return self.council_ids or [r.id for r in self.routes]


def _answer_system() -> str:
    return "Answer the question directly and follow any output-format instructions exactly."


async def _single(ctx: EvalContext, model_id: str, item: EvalItem) -> Prediction:
    route = ctx.route(model_id)
    adapter = ctx.adapters[route.provider]
    started = time.perf_counter()
    messages = [
        ChatMessage(role="system", content=_answer_system()),
        ChatMessage(role="user", content=item.question),
    ]
    content, usage, _ = await adapter.complete(route, messages)
    return Prediction(
        config=f"single:{model_id}",
        item_id=item.id,
        suite=item.suite,
        answer=content,
        latency_s=round(time.perf_counter() - started, 3),
        tokens=(usage.total_tokens or 0) if usage else 0,
        cost_usd=(usage.cost or 0.0) if usage else 0.0,
    )


async def _self_consistency(ctx: EvalContext, model_id: str, k: int, item: EvalItem) -> Prediction:
    route = ctx.route(model_id)
    adapter = ctx.adapters[route.provider]
    started = time.perf_counter()
    messages = [
        ChatMessage(role="system", content=_answer_system()),
        ChatMessage(role="user", content=item.question),
    ]
    answers: list[str] = []
    tokens = 0
    cost = 0.0
    for _ in range(max(1, k)):
        content, usage, _ = await adapter.complete(route, messages)
        answers.append(content)
        if usage:
            tokens += usage.total_tokens or 0
            cost += usage.cost or 0.0
    # Majority vote on the normalized answer; keep a representative raw answer from the winner.
    keys = [_normalize(a) for a in answers]
    winner_key, count = Counter(keys).most_common(1)[0]
    representative = next(a for a, key in zip(answers, keys) if key == winner_key)
    return Prediction(
        config=f"self_consistency:{model_id}:{k}",
        item_id=item.id,
        suite=item.suite,
        answer=representative,
        confidence=count / len(answers),
        latency_s=round(time.perf_counter() - started, 3),
        tokens=tokens,
        cost_usd=round(cost, 6),
    )


async def _senate(ctx: EvalContext, item: EvalItem) -> Prediction:
    ids = ctx.council_model_ids()
    if len(ids) < 3:
        return Prediction(config="senate", item_id=item.id, suite=item.suite,
                           error="senate requires >= 3 models")
    service = SenateService(routes=ctx.routes, adapters=ctx.adapters, store=ctx.store)
    started = time.perf_counter()
    run = await service.run(SenateRequest(
        prompt=item.question, selected_model_ids=ids, leader_model_id=ids[0]
    ))
    return Prediction(
        config="senate",
        item_id=item.id,
        suite=item.suite,
        answer=run.final_synthesis.content,
        latency_s=round(time.perf_counter() - started, 3),
        tokens=run.total_tokens,
        cost_usd=run.total_cost_usd or 0.0,
    )


async def _council(ctx: EvalContext, config: str, item: EvalItem) -> Prediction:
    overrides = dict(_ABLATIONS[config])
    no_tools = overrides.pop("no_tools", False)
    service = CouncilService(
        routes=ctx.routes,
        adapters=ctx.adapters,
        store=ctx.store,
        tool_registry={} if no_tools else ctx.tool_registry,
        orchestrator_model_id=ctx.orchestrator_model_id,
        debate_enabled=ctx.debate_enabled and overrides.get("debate_enabled", True),
        enable_critique=overrides.get("enable_critique", True),
        enable_election=overrides.get("enable_election", True),
    )
    started = time.perf_counter()
    run = await service.run(CouncilRequest(prompt=item.question, selected_model_ids=ctx.council_model_ids()))
    if run.reintegration and run.reintegration.unified_answer:
        answer = run.reintegration.unified_answer
    elif run.synthesis:
        answer = run.synthesis.direct_answer
    else:
        answer = ""
    grade = run.confidence_grade
    return Prediction(
        config=config,
        item_id=item.id,
        suite=item.suite,
        answer=answer,
        grade=grade,
        confidence=GRADE_PROB.get(grade) if grade else None,
        latency_s=round(time.perf_counter() - started, 3),
        tokens=run.total_tokens,
        cost_usd=run.total_cost_usd or 0.0,
    )


async def run_config(config: str, item: EvalItem, ctx: EvalContext) -> Prediction:
    """Dispatch a config string to its runner. Errors are captured, not raised."""
    try:
        if config.startswith("single:"):
            return await _single(ctx, config.split(":", 1)[1], item)
        if config.startswith("self_consistency:"):
            _, model_id, k = config.split(":", 2)
            return await _self_consistency(ctx, model_id, int(k), item)
        if config == "senate":
            return await _senate(ctx, item)
        if config in _ABLATIONS:
            return await _council(ctx, config, item)
        raise ValueError(f"Unknown eval config: {config}")
    except Exception as exc:  # noqa: BLE001 — the harness records failures per (config, item)
        return Prediction(config=config, item_id=item.id, suite=item.suite, error=str(exc))
