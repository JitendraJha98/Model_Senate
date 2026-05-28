from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone
from uuid import uuid4

from backend.providers import ProviderAdapter
from backend.schemas import (
    AggregateRanking,
    ChatMessage,
    FinalSynthesis,
    ModelOutput,
    ModelRoute,
    PeerReview,
    RankingEntry,
    SenateRequest,
    SenateRun,
)
from backend.storage import ConversationStore


FIRST_OPINION_SYSTEM = """You are a senator in Model_Senate, a multi-model research council.
Answer independently before seeing other models. Prioritize factual accuracy, useful nuance,
and calibrated uncertainty. When the topic is high-stakes, name what must be verified."""

REVIEW_SYSTEM = """You are anonymously reviewing other AI model answers for Model_Senate.
You will see anonymous labels only. Do not infer, mention, or reward model/provider identities.
Evaluate accuracy, completeness, reasoning quality, calibration, and useful dissent.
Your final section must be parseable and must contain no provider or model names."""

SYNTHESIS_SYSTEM = """You are the leader model for Model_Senate. Produce one unified answer from
multiple model opinions, anonymous peer reviews, and aggregate rankings. Truth beats majority vote.
Make agreement, disagreement, uncertainty, and recommended next checks clear. Do not hide unresolved conflicts."""


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
        if len(set(request.selected_model_ids)) != len(request.selected_model_ids):
            raise ValueError("Selected model IDs must be unique")
        if request.leader_model_id not in request.selected_model_ids:
            raise ValueError("Leader model must be one of the selected models")
        selected = [self._route_or_raise(model_id) for model_id in request.selected_model_ids]
        leader = self._route_or_raise(request.leader_model_id)

        first_opinions = await asyncio.gather(
            *(self._first_opinion(route, request.prompt, request.system_context) for route in selected)
        )
        successful = [opinion for opinion in first_opinions if opinion.status == "completed" and opinion.content.strip()]

        peer_reviews: list[PeerReview] = []
        if len(successful) >= 2:
            successful_ids = {opinion.model_id for opinion in successful}
            peer_reviews = await asyncio.gather(
                *(self._peer_review(route, successful) for route in selected if route.id in successful_ids)
            )

        aggregate_rankings = calculate_aggregate_rankings(peer_reviews, successful)
        final_synthesis = await self._final_synthesis(
            leader,
            request.prompt,
            first_opinions,
            peer_reviews,
            aggregate_rankings,
        )
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
            aggregate_rankings=aggregate_rankings,
            final_synthesis=final_synthesis,
            errors=[error for error in errors if error],
            total_latency_ms=int((time.perf_counter() - started) * 1000),
            metadata={
                "successful_first_opinions": len(successful),
                "pipeline": "three-stage-full",
                "ranking_method": "anonymous-peer-review-average-rank",
            },
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
                parsed_ranking=parse_ranking_from_text(content, alias_map, opinions),
                content=content,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            return PeerReview(
                reviewer_model_id=reviewer.id,
                reviewer_display_name=reviewer.display_name,
                status="failed",
                anonymized_map=alias_map,
                parsed_ranking=[],
                error=str(exc),
            )

    async def _final_synthesis(
        self,
        leader: ModelRoute,
        prompt: str,
        opinions: list[ModelOutput],
        reviews: list[PeerReview],
        aggregate_rankings: list[AggregateRanking],
    ) -> FinalSynthesis:
        try:
            content, _, latency_ms = await self.adapters[leader.provider].complete(
                leader,
                [
                    ChatMessage(role="system", content=SYNTHESIS_SYSTEM),
                    ChatMessage(
                        role="user",
                        content=build_synthesis_prompt(prompt, opinions, reviews, aggregate_rankings),
                    ),
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
    response_block = "\n\n---\n\n".join(blocks)
    example_labels = [f"Response {chr(65 + index)}" for index in range(len(opinions))]
    example_ranking = "\n".join(
        f"{index + 1}. {label} - short reason" for index, label in enumerate(reversed(example_labels))
    )
    return f"""Review and rank these anonymous responses. Do not mention model names.

Process:
1. Evaluate each response individually.
2. Note factual strengths, missing context, unsupported claims, and useful dissent.
3. End with exactly this section:

FINAL RANKING:
{example_ranking}

Use only labels that appear below. Do not add text after the FINAL RANKING section.

Anonymous responses:

{response_block}
"""


def parse_ranking_from_text(
    text: str,
    label_to_model: dict[str, str],
    opinions: list[ModelOutput],
) -> list[RankingEntry]:
    display_names = {opinion.model_id: opinion.display_name for opinion in opinions}
    valid_labels = {normalize_response_label(label) for label in label_to_model}
    ranking_text = text
    marker = re.search(r"FINAL\s+RANKING\s*:?", text, flags=re.IGNORECASE)
    if marker:
        ranking_text = text[marker.end() :]

    entries: list[RankingEntry] = []
    seen: set[str] = set()
    line_pattern = re.compile(
        r"(?:^|\s)(?:\d+\s*[\.\)]\s*)?(Response\s+[A-Z])\b\s*(?:[-:]\s*(.*))?",
        flags=re.IGNORECASE,
    )

    for line in ranking_text.splitlines():
        match = line_pattern.search(line.strip())
        if not match:
            continue
        label = normalize_response_label(match.group(1))
        if label not in valid_labels or label in seen:
            continue
        model_id = label_to_model[label]
        seen.add(label)
        entries.append(
            RankingEntry(
                rank=len(entries) + 1,
                response_label=label,
                model_id=model_id,
                display_name=display_names.get(model_id),
                reason=(match.group(2) or "").strip() or None,
            )
        )

    if entries:
        return entries

    for match in re.finditer(r"Response\s+[A-Z]", ranking_text, flags=re.IGNORECASE):
        label = normalize_response_label(match.group(0))
        if label not in valid_labels or label in seen:
            continue
        model_id = label_to_model[label]
        seen.add(label)
        entries.append(
            RankingEntry(
                rank=len(entries) + 1,
                response_label=label,
                model_id=model_id,
                display_name=display_names.get(model_id),
            )
        )
    return entries


def calculate_aggregate_rankings(
    reviews: list[PeerReview],
    opinions: list[ModelOutput],
) -> list[AggregateRanking]:
    display_names = {opinion.model_id: opinion.display_name for opinion in opinions}
    positions: dict[str, list[int]] = {opinion.model_id: [] for opinion in opinions}
    for review in reviews:
        if review.status != "completed":
            continue
        for entry in review.parsed_ranking:
            if entry.model_id in positions:
                positions[entry.model_id].append(entry.rank)

    candidate_count = max(len(opinions), 1)
    aggregates: list[AggregateRanking] = []
    for model_id, ranks in positions.items():
        if not ranks:
            continue
        average_rank = sum(ranks) / len(ranks)
        confidence_score = max(0.0, min(1.0, (candidate_count - average_rank + 1) / candidate_count))
        aggregates.append(
            AggregateRanking(
                model_id=model_id,
                display_name=display_names.get(model_id, model_id),
                average_rank=round(average_rank, 2),
                vote_count=len(ranks),
                first_place_votes=sum(1 for rank in ranks if rank == 1),
                best_rank=min(ranks),
                worst_rank=max(ranks),
                confidence_score=round(confidence_score, 3),
            )
        )

    return sorted(aggregates, key=lambda item: (item.average_rank, -item.first_place_votes, item.display_name))


def normalize_response_label(label: str) -> str:
    match = re.search(r"Response\s+([A-Z])", label, flags=re.IGNORECASE)
    if not match:
        return label.strip()
    return f"Response {match.group(1).upper()}"


def build_synthesis_prompt(
    prompt: str,
    opinions: list[ModelOutput],
    reviews: list[PeerReview],
    aggregate_rankings: list[AggregateRanking],
) -> str:
    opinion_blocks = []
    for opinion in opinions:
        label = opinion.display_name
        body = opinion.content if opinion.status == "completed" else f"FAILED: {opinion.error}"
        opinion_blocks.append(f"### {label}\n{body}")

    review_blocks = []
    for review in reviews:
        body = review.content if review.status == "completed" else f"FAILED: {review.error}"
        review_blocks.append(f"### Review by {review.reviewer_display_name}\n{body}")

    aggregate_block = "\n".join(
        f"{index + 1}. {ranking.display_name} - avg rank {ranking.average_rank}, "
        f"{ranking.first_place_votes} first-place votes, confidence {ranking.confidence_score}"
        for index, ranking in enumerate(aggregate_rankings)
    )
    if not aggregate_block:
        aggregate_block = "No aggregate ranking could be calculated."

    return f"""Original user query:
{prompt}

First opinions:
{chr(10).join(opinion_blocks)}

Peer reviews:
{chr(10).join(review_blocks)}

Aggregate anonymous ranking:
{aggregate_block}

Write the final answer with these sections:
1. Direct answer
2. Where the models agree
3. Where they differ or remain uncertain
4. Recommended next checks

Use the rankings as weak evidence about response quality, not as a substitute for checking claims.
"""
