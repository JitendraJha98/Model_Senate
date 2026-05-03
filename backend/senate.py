from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from uuid import uuid4

from backend.providers import ProviderAdapter
from backend.schemas import (
    ChatMessage,
    FinalSynthesis,
    ModelOutput,
    ModelRoute,
    PeerReview,
    SenateRequest,
    SenateRun,
)
from backend.storage import ConversationStore


FIRST_OPINION_SYSTEM = """You are a member of Model_Senate. Answer the user's research query independently.
Be accurate, explicit about uncertainty, and avoid overclaiming."""

REVIEW_SYSTEM = """You are anonymously reviewing other AI model answers for Model_Senate.
Do not infer or mention model/provider identities. Rank the anonymous responses for accuracy,
completeness, reasoning quality, and useful dissent. Be concise but specific."""

SYNTHESIS_SYSTEM = """You are the leader model for Model_Senate. Produce one unified answer from
multiple model opinions and peer reviews. Make agreement, disagreement, uncertainty, and recommended
next checks clear. Do not hide unresolved conflicts."""


class SenateService:
    def __init__(
        self,
        routes: list[ModelRoute],
        adapters: dict[str, ProviderAdapter],
        store: ConversationStore,
    ):
        self.routes = {route.id: route for route in routes}
        self.adapters = adapters
        self.store = store

    async def run(self, request: SenateRequest) -> SenateRun:
        started = time.perf_counter()
        created_at = datetime.now(timezone.utc)
        selected = [self._route_or_raise(model_id) for model_id in request.selected_model_ids]
        leader = self._route_or_raise(request.leader_model_id)

        first_opinions = await asyncio.gather(
            *(self._first_opinion(route, request.prompt, request.system_context) for route in selected)
        )
        successful = [opinion for opinion in first_opinions if opinion.status == "completed" and opinion.content.strip()]

        peer_reviews: list[PeerReview] = []
        if len(successful) >= 2:
            peer_reviews = await asyncio.gather(*(self._peer_review(route, successful) for route in selected))

        final_synthesis = await self._final_synthesis(leader, request.prompt, first_opinions, peer_reviews)
        errors = [
            item.error
            for item in [*first_opinions, *peer_reviews, final_synthesis]
            if item.error
        ]
        status = "completed"
        if final_synthesis.status == "failed" or not successful:
            status = "failed"
        elif errors:
            status = "partial_failed"

        completed_at = datetime.now(timezone.utc)
        run = SenateRun(
            id=str(uuid4()),
            status=status,
            created_at=created_at,
            completed_at=completed_at,
            prompt=request.prompt,
            selected_models=selected,
            leader_model=leader,
            first_opinions=first_opinions,
            peer_reviews=peer_reviews,
            final_synthesis=final_synthesis,
            errors=[error for error in errors if error],
            total_latency_ms=int((time.perf_counter() - started) * 1000),
            metadata={"successful_first_opinions": len(successful), "pipeline": "three-stage-full"},
        )
        self.store.save(run)
        return run

    async def _first_opinion(self, route: ModelRoute, prompt: str, system_context: str | None) -> ModelOutput:
        system = FIRST_OPINION_SYSTEM
        if system_context:
            system = f"{system}\n\nUser-provided context:\n{system_context}"
        messages = [ChatMessage(role="system", content=system), ChatMessage(role="user", content=prompt)]
        try:
            content, usage, latency_ms = await self.adapters[route.provider].complete(route, messages)
            return ModelOutput(
                model_id=route.id,
                display_name=route.display_name,
                provider=route.provider,
                status="completed",
                content=content,
                latency_ms=latency_ms,
                usage=usage,
            )
        except Exception as exc:
            return ModelOutput(
                model_id=route.id,
                display_name=route.display_name,
                provider=route.provider,
                status="failed",
                error=str(exc),
            )

    async def _peer_review(self, reviewer: ModelRoute, opinions: list[ModelOutput]) -> PeerReview:
        reviewable = [opinion for opinion in opinions if opinion.model_id != reviewer.id]
        alias_map = {f"Response {chr(65 + index)}": opinion.model_id for index, opinion in enumerate(reviewable)}
        prompt = build_review_prompt(reviewable)
        try:
            content, _, latency_ms = await self.adapters[reviewer.provider].complete(
                reviewer,
                [ChatMessage(role="system", content=REVIEW_SYSTEM), ChatMessage(role="user", content=prompt)],
            )
            return PeerReview(
                reviewer_model_id=reviewer.id,
                reviewer_display_name=reviewer.display_name,
                status="completed",
                anonymized_map=alias_map,
                content=content,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            return PeerReview(
                reviewer_model_id=reviewer.id,
                reviewer_display_name=reviewer.display_name,
                status="failed",
                anonymized_map=alias_map,
                error=str(exc),
            )

    async def _final_synthesis(
        self,
        leader: ModelRoute,
        prompt: str,
        opinions: list[ModelOutput],
        reviews: list[PeerReview],
    ) -> FinalSynthesis:
        try:
            content, _, latency_ms = await self.adapters[leader.provider].complete(
                leader,
                [
                    ChatMessage(role="system", content=SYNTHESIS_SYSTEM),
                    ChatMessage(role="user", content=build_synthesis_prompt(prompt, opinions, reviews)),
                ],
            )
            return FinalSynthesis(
                leader_model_id=leader.id,
                leader_display_name=leader.display_name,
                status="completed",
                content=content,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            return FinalSynthesis(
                leader_model_id=leader.id,
                leader_display_name=leader.display_name,
                status="failed",
                error=str(exc),
            )

    def _route_or_raise(self, model_id: str) -> ModelRoute:
        route = self.routes.get(model_id)
        if not route:
            raise ValueError(f"Unknown model route: {model_id}")
        return route


def build_review_prompt(opinions: list[ModelOutput]) -> str:
    blocks = []
    for index, opinion in enumerate(opinions):
        alias = f"Response {chr(65 + index)}"
        blocks.append(f"{alias}:\n{opinion.content}")
    return "Review and rank these anonymous responses. Do not mention model names.\n\n" + "\n\n---\n\n".join(blocks)


def build_synthesis_prompt(prompt: str, opinions: list[ModelOutput], reviews: list[PeerReview]) -> str:
    opinion_blocks = []
    for opinion in opinions:
        label = opinion.display_name
        body = opinion.content if opinion.status == "completed" else f"FAILED: {opinion.error}"
        opinion_blocks.append(f"### {label}\n{body}")

    review_blocks = []
    for review in reviews:
        body = review.content if review.status == "completed" else f"FAILED: {review.error}"
        review_blocks.append(f"### Review by {review.reviewer_display_name}\n{body}")

    return f"""Original user query:
{prompt}

First opinions:
{chr(10).join(opinion_blocks)}

Peer reviews:
{chr(10).join(review_blocks)}

Write the final answer with these sections:
1. Direct answer
2. Where the models agree
3. Where they differ or remain uncertain
4. Recommended next checks
"""

