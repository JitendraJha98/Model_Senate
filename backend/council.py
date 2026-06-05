from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from uuid import uuid4

from backend.election import elect_leader
from backend.orchestrator import classify_query, fallback_plan
from backend.providers import ProviderAdapter
from backend.reintegrator import (
    build_reintegration_prompt,
    detect_contradictions,
    parse_reintegration_result,
)
from backend.roles import build_critique_prompt, build_system_prompt, critique_roles
from backend.schemas import (
    AgentOpinion,
    ChatMessage,
    Claim,
    CouncilCritique,
    CouncilRequest,
    CouncilRun,
    CouncilSynthesis,
    LeaderElection,
    ModelRoute,
    OrchestrationPlan,
    ProvenanceEntry,
    ReintegrationOutput,
    SubQuestion,
    SynthesisValidation,
    ToolResult,
)
from backend.storage import ConversationStore
from backend.streaming import CouncilEventStream
from backend.tools import ToolRegistry, inject_tool_results
from backend.validator import build_validation_prompt, parse_validation_result


class CouncilService:
    def __init__(
        self,
        routes: list[ModelRoute],
        adapters: dict[str, ProviderAdapter],
        store: ConversationStore,
        tool_registry: ToolRegistry,
        orchestrator_model_id: str,
        synthesis_retry_on_failure: bool = True,
    ):
        self.routes = {route.id: route for route in routes}
        self.adapters = adapters
        self.store = store
        self.tool_registry = tool_registry
        self.orchestrator_model_id = orchestrator_model_id
        self.synthesis_retry_on_failure = synthesis_retry_on_failure

    async def run(
        self,
        request: CouncilRequest,
        run_id: str | None = None,
        stream: CouncilEventStream | None = None,
    ) -> CouncilRun:
        started = time.perf_counter()
        created_at = datetime.now(timezone.utc)
        rid = run_id or str(uuid4())

        if len(set(request.selected_model_ids)) != len(request.selected_model_ids):
            raise ValueError("Selected model IDs must be unique")

        selected = [self._route_or_raise(mid) for mid in request.selected_model_ids]

        plan = await self._stage0_orchestrate(request, selected)
        await self._emit(stream, "plan_ready", plan.model_dump())

        if plan.is_multi_part and plan.sub_questions:
            run = await self._run_multi_part(rid, request, selected, plan, stream, started, created_at)
        else:
            run = await self._run_single(rid, request, selected, plan, stream, started, created_at)

        self.store.save(run)
        await self._emit(stream, "run_complete", run.model_dump())
        return run

    # ------------------------------------------------------------------
    # Multi-part path (Stage 6)
    # ------------------------------------------------------------------

    async def _run_multi_part(
        self,
        run_id: str,
        request: CouncilRequest,
        selected: list[ModelRoute],
        plan: OrchestrationPlan,
        stream: CouncilEventStream | None,
        started: float,
        created_at: datetime,
    ) -> CouncilRun:
        sub_runs = await asyncio.gather(*(
            self._run_sub_question(sq, request, selected, stream)
            for sq in plan.sub_questions
        ))

        reintegration: ReintegrationOutput | None = None
        if sub_runs:
            contradictions = detect_contradictions(list(sub_runs))
            reintegration = await self._stage6_reintegrate(list(sub_runs), request.prompt, contradictions, selected)
            await self._emit(stream, "reintegration_ready", reintegration.model_dump())

        # Inherit lowest confidence grade
        grades = [r.confidence_grade for r in sub_runs if r.confidence_grade]
        order = ["F", "D", "C", "B", "A"]
        final_grade = min(grades, key=lambda g: order.index(g)) if grades else None

        status = "completed"
        if all(r.status == "failed" for r in sub_runs):
            status = "failed"
        elif any(r.status in {"failed", "partial_failed"} for r in sub_runs):
            status = "partial_failed"

        completed_at = datetime.now(timezone.utc)
        return CouncilRun(
            id=run_id,
            status=status,
            orchestration_plan=plan,
            agent_opinions=[],
            council_critiques=[],
            sub_runs=list(sub_runs),
            reintegration=reintegration,
            confidence_grade=final_grade,
            created_at=created_at,
            completed_at=completed_at,
            prompt=request.prompt,
            selected_models=selected,
            total_latency_ms=int((time.perf_counter() - started) * 1000),
            total_tokens=sum(r.total_tokens for r in sub_runs),
            total_cost_usd=(
                round(sum(r.total_cost_usd for r in sub_runs if r.total_cost_usd), 6)
                if any(r.total_cost_usd for r in sub_runs)
                else None
            ),
            metadata={"pipeline": "model-council", "mode": "multi_part"},
        )

    async def _run_sub_question(
        self,
        sub_q: SubQuestion,
        request: CouncilRequest,
        selected: list[ModelRoute],
        stream: CouncilEventStream | None,
    ) -> CouncilRun:
        sub_request = CouncilRequest(
            prompt=sub_q.question,
            selected_model_ids=request.selected_model_ids,
            system_context=request.system_context,
        )
        # Force non-multi-part plan for sub-questions
        sub_plan = fallback_plan(sub_q.question, request.selected_model_ids, self.tool_registry)
        sub_plan = sub_plan.model_copy(update={"query_type": sub_q.query_type, "is_multi_part": False})

        rid = str(uuid4())
        started = time.perf_counter()
        created_at = datetime.now(timezone.utc)
        return await self._run_single(rid, sub_request, selected, sub_plan, stream, started, created_at)

    # ------------------------------------------------------------------
    # Single pipeline (Stages 1–5)
    # ------------------------------------------------------------------

    async def _run_single(
        self,
        run_id: str,
        request: CouncilRequest,
        selected: list[ModelRoute],
        plan: OrchestrationPlan,
        stream: CouncilEventStream | None,
        started: float,
        created_at: datetime,
    ) -> CouncilRun:
        opinions = await self._stage1_first_opinions(plan, request, selected, stream)
        successful = [o for o in opinions if o.status in {"completed", "parse_failed"} and o.content.strip()]

        if not successful:
            completed_at = datetime.now(timezone.utc)
            return CouncilRun(
                id=run_id,
                status="failed",
                orchestration_plan=plan,
                agent_opinions=opinions,
                council_critiques=[],
                created_at=created_at,
                completed_at=completed_at,
                prompt=request.prompt,
                selected_models=selected,
                errors=[o.error or "Model failed" for o in opinions if o.status == "failed"],
                total_latency_ms=int((time.perf_counter() - started) * 1000),
                metadata={"pipeline": "model-council", "failure": "all_stage1_failed"},
            )

        critiques = await self._stage2_critique(successful, stream) if len(successful) >= 2 else []

        election = elect_leader(successful, critiques)
        await self._emit(stream, "leader_elected", election.model_dump())

        synthesis = await self._stage4_synthesize(election, plan, opinions, critiques, request)
        if synthesis.status == "failed" and self.synthesis_retry_on_failure:
            retry = election.model_copy(update={
                "elected_model_id": election.runner_up_model_id,
                "elected_display_name": election.runner_up_display_name,
            })
            synthesis = await self._stage4_synthesize(retry, plan, opinions, critiques, request)
        await self._emit(stream, "synthesis_ready", synthesis.model_dump())

        validation = await self._stage5_validate(election, synthesis, opinions, critiques, request.prompt)
        await self._emit(stream, "validation_result", validation.model_dump())

        provenance = self._build_provenance_tree(synthesis, opinions, critiques)
        grade = synthesis.confidence_grade or self._compute_final_grade(synthesis, validation)

        errors = [
            item.error
            for item in [*opinions, *critiques, synthesis, validation]
            if getattr(item, "error", None)
        ]

        if synthesis.status == "failed":
            status = "failed"
        elif validation.verdict == "flagged" or validation.status == "failed":
            status = "approved_with_caveats"
        elif errors:
            status = "partial_failed"
        else:
            status = "completed"

        completed_at = datetime.now(timezone.utc)
        return CouncilRun(
            id=run_id,
            status=status,
            orchestration_plan=plan,
            agent_opinions=opinions,
            council_critiques=critiques,
            leader_election=election,
            synthesis=synthesis,
            validation=validation,
            provenance_tree=provenance,
            confidence_grade=grade,
            created_at=created_at,
            completed_at=completed_at,
            prompt=request.prompt,
            selected_models=selected,
            errors=[e for e in errors if e],
            total_latency_ms=int((time.perf_counter() - started) * 1000),
            total_tokens=sum((o.usage.total_tokens or 0) for o in [*opinions, synthesis] if o.usage),
            total_cost_usd=_sum_cost([*opinions, synthesis]),
            metadata={"pipeline": "model-council", "successful_first_opinions": len(successful)},
        )

    # ------------------------------------------------------------------
    # Stage 0
    # ------------------------------------------------------------------

    async def _stage0_orchestrate(
        self, request: CouncilRequest, selected: list[ModelRoute]
    ) -> OrchestrationPlan:
        orchestrator_route = self.routes.get(self.orchestrator_model_id)
        adapter = self.adapters.get(orchestrator_route.provider) if orchestrator_route else None
        return await classify_query(
            request.prompt, selected, orchestrator_route, adapter, self.tool_registry
        )

    # ------------------------------------------------------------------
    # Stage 1 — First Opinions
    # ------------------------------------------------------------------

    async def _stage1_first_opinions(
        self,
        plan: OrchestrationPlan,
        request: CouncilRequest,
        selected: list[ModelRoute],
        stream: CouncilEventStream | None,
    ) -> list[AgentOpinion]:
        async def run_one(route: ModelRoute) -> AgentOpinion:
            opinion = await self._stage1_single_opinion(
                route,
                plan.role_assignments.get(route.id, "Independent Expert"),
                plan.tool_assignments.get(route.id, []),
                plan,
                request,
                stream,
            )
            await self._emit(stream, "agent_opinion", opinion.model_dump())
            return opinion

        return list(await asyncio.gather(*(run_one(route) for route in selected)))

    async def _stage1_single_opinion(
        self,
        route: ModelRoute,
        role: str,
        tools: list[str],
        plan: OrchestrationPlan,
        request: CouncilRequest,
        stream: CouncilEventStream | None = None,
    ) -> AgentOpinion:
        system = build_system_prompt(role, plan.query_type)
        if request.system_context:
            system = f"{system}\n\nUser-provided context:\n{request.system_context}"
        adapter = self.adapters[route.provider]
        messages = [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=request.prompt),
        ]

        async def on_delta(delta: str) -> None:
            await self._emit(stream, "opinion_token", {"model_id": route.id, "delta": delta})

        use_stream = stream is not None and route.supports_streaming
        try:
            content, usage, latency_ms = await self._complete(
                adapter, route, messages, on_delta if use_stream else None
            )
            allowed = {name: self.tool_registry[name] for name in tools if name in self.tool_registry}
            content_with_tools, tool_results = await inject_tool_results(content, allowed)
            return _parse_opinion(route, role, content_with_tools, latency_ms, usage, tool_results)
        except Exception as exc:
            return AgentOpinion(
                model_id=route.id,
                display_name=route.display_name,
                provider=route.provider,
                role=role,
                status="failed",
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Stage 2 — Cross-Model Critique (batch: one call per reviewer)
    # ------------------------------------------------------------------

    async def _stage2_critique(
        self, opinions: list[AgentOpinion], stream: CouncilEventStream | None
    ) -> list[CouncilCritique]:
        roles = critique_roles(len(opinions))
        labels = [chr(65 + i) for i in range(len(opinions))]  # A, B, C, …

        async def review_all(reviewer: AgentOpinion, critique_role: str) -> list[CouncilCritique]:
            targets = [o for o in opinions if o.model_id != reviewer.model_id]
            target_labels = [labels[opinions.index(o)] for o in targets]
            anonymized_map = {f"Agent {label}": t.model_id for label, t in zip(target_labels, targets)}

            route = self._route_or_raise(reviewer.model_id)
            try:
                content, _, latency_ms = await self.adapters[route.provider].complete(
                    route,
                    [
                        ChatMessage(
                            role="system",
                            content="You are a Model Council critique agent. Return only JSON.",
                        ),
                        ChatMessage(
                            role="user",
                            content=build_critique_prompt(critique_role, reviewer, targets, anonymized_map),
                        ),
                    ],
                )
                batch = _parse_batch_critique(
                    reviewer, critique_role, targets, anonymized_map, content, latency_ms
                )
            except Exception as exc:
                batch = [
                    CouncilCritique(
                        reviewer_model_id=reviewer.model_id,
                        reviewer_display_name=reviewer.display_name,
                        reviewer_critique_role=critique_role,
                        target_model_id=t.model_id,
                        target_display_name=t.display_name,
                        status="failed",
                        error=str(exc),
                    )
                    for t in targets
                ]

            for critique in batch:
                await self._emit(stream, "critique_scored", critique.model_dump())
            return batch

        nested = await asyncio.gather(*(
            review_all(opinions[i], roles[i].value) for i in range(len(opinions))
        ))
        return [item for group in nested for item in group]

    # ------------------------------------------------------------------
    # Stage 4 — Leader Synthesis
    # ------------------------------------------------------------------

    async def _stage4_synthesize(
        self,
        election: LeaderElection,
        plan: OrchestrationPlan,
        opinions: list[AgentOpinion],
        critiques: list[CouncilCritique],
        request: CouncilRequest,
    ) -> CouncilSynthesis:
        leader = self._route_or_raise(election.elected_model_id)
        try:
            content, usage, latency_ms = await self.adapters[leader.provider].complete(
                leader,
                [
                    ChatMessage(role="system", content=_synthesis_system()),
                    ChatMessage(
                        role="user",
                        content=_synthesis_prompt(request.prompt, plan, opinions, critiques, election),
                    ),
                ],
            )
            return _parse_synthesis(leader, content, latency_ms, usage)
        except Exception as exc:
            return CouncilSynthesis(
                leader_model_id=leader.id,
                leader_display_name=leader.display_name,
                status="failed",
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Stage 5 — Synthesis Validation
    # ------------------------------------------------------------------

    async def _stage5_validate(
        self,
        election: LeaderElection,
        synthesis: CouncilSynthesis,
        opinions: list[AgentOpinion],
        critiques: list[CouncilCritique],
        original_query: str,
    ) -> SynthesisValidation:
        if synthesis.status == "failed":
            return SynthesisValidation(status="failed", error=synthesis.error)
        validator_id = election.runner_up_model_id
        validator = self._route_or_raise(validator_id)
        try:
            content, _, latency_ms = await self.adapters[validator.provider].complete(
                validator,
                [
                    ChatMessage(
                        role="system",
                        content="You validate Model Council syntheses. Return only JSON.",
                    ),
                    ChatMessage(
                        role="user",
                        content=build_validation_prompt(synthesis, critiques, original_query),
                    ),
                ],
            )
            return parse_validation_result(content, validator.id, validator.display_name, latency_ms)
        except Exception as exc:
            return SynthesisValidation(
                validator_model_id=validator.id,
                validator_display_name=validator.display_name,
                status="failed",
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Stage 6 — Re-integration (multi-part only)
    # ------------------------------------------------------------------

    async def _stage6_reintegrate(
        self,
        sub_runs: list[CouncilRun],
        original_prompt: str,
        contradictions: list[str],
        selected: list[ModelRoute],
    ) -> ReintegrationOutput:
        # Use the first available leader from sub-runs, else first selected route
        leader_id = next(
            (r.leader_election.elected_model_id for r in sub_runs if r.leader_election),
            selected[0].id if selected else None,
        )
        if not leader_id or leader_id not in self.routes:
            leader_id = selected[0].id if selected else None
        if not leader_id:
            return ReintegrationOutput(status="failed", error="No route available for re-integration")

        leader = self.routes[leader_id]
        prompt_text = build_reintegration_prompt(sub_runs, original_prompt, contradictions)
        started = time.perf_counter()
        try:
            content, _, _ = await self.adapters[leader.provider].complete(
                leader,
                [
                    ChatMessage(
                        role="system",
                        content="You are the Re-integration Agent in Model Council. Return only JSON.",
                    ),
                    ChatMessage(role="user", content=prompt_text),
                ],
            )
            return parse_reintegration_result(
                content,
                leader.id,
                leader.display_name,
                [r.id for r in sub_runs],
                int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:
            return ReintegrationOutput(
                model_id=leader.id,
                display_name=leader.display_name,
                status="failed",
                unified_answer="\n\n---\n\n".join(
                    r.synthesis.direct_answer for r in sub_runs if r.synthesis and r.synthesis.direct_answer
                ),
                sub_run_ids=[r.id for r in sub_runs],
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Provenance + grading helpers
    # ------------------------------------------------------------------

    def _build_provenance_tree(
        self,
        synthesis: CouncilSynthesis,
        opinions: list[AgentOpinion],
        critiques: list[CouncilCritique],
    ) -> dict[str, ProvenanceEntry]:
        reviewers_by_target: dict[str, list[str]] = {}
        challengers_by_target: dict[str, list[str]] = {}
        for c in critiques:
            if c.weaknesses or c.corrective_additions:
                challengers_by_target.setdefault(c.target_model_id, []).append(c.reviewer_model_id)
            else:
                reviewers_by_target.setdefault(c.target_model_id, []).append(c.reviewer_model_id)

        entries: dict[str, ProvenanceEntry] = {}
        for opinion in opinions:
            for claim in opinion.key_claims:
                key = f"{opinion.model_id}::{claim.text[:60]}"
                entries[key] = ProvenanceEntry(
                    claim_text=claim.text,
                    source_model_ids=[opinion.model_id],
                    validated_by=reviewers_by_target.get(opinion.model_id, []),
                    challenged_by=challengers_by_target.get(opinion.model_id, []),
                    tool_verified=claim.verified,
                    tool_result_summary=claim.source if claim.verified else None,
                )
        return entries

    def _compute_final_grade(
        self, synthesis: CouncilSynthesis, validation: SynthesisValidation
    ) -> str | None:
        if synthesis.status == "failed":
            return "F"
        if validation.verdict == "approved":
            return "A"
        if validation.verdict == "flagged":
            return "C"
        return "B"

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    async def _complete(self, adapter, route, messages, on_delta=None):
        """Stream token deltas when requested and supported; otherwise a single response.

        A streaming failure falls back to the retry-backed `complete()` path.
        """
        if on_delta is not None and hasattr(adapter, "complete_streamed"):
            try:
                return await adapter.complete_streamed(route, messages, on_delta)
            except Exception:
                pass
        return await adapter.complete(route, messages)

    def _route_or_raise(self, model_id: str) -> ModelRoute:
        route = self.routes.get(model_id)
        if not route:
            raise ValueError(f"Unknown model route: {model_id}")
        return route

    async def _emit(self, stream: CouncilEventStream | None, event: str, payload: dict) -> None:
        if stream:
            await stream.emit(event, payload)


# ---------------------------------------------------------------------------
# Stage 1 parsing helpers
# ---------------------------------------------------------------------------

def _parse_opinion(
    route: ModelRoute,
    role: str,
    content: str,
    latency_ms: int | None,
    usage,
    tool_results: list[ToolResult],
) -> AgentOpinion:
    # Find the COUNCIL_OUTPUT: marker and extract the JSON block after it
    marker_match = re.search(r"COUNCIL_OUTPUT:\s*", content, re.IGNORECASE)
    if marker_match:
        after_marker = content[marker_match.end():]
        try:
            data = json.loads(_extract_json(after_marker))
            verified_tools = {r.tool for r in tool_results if r.success}
            claims = [
                Claim(
                    text=str(c.get("text", "") if isinstance(c, dict) else c),
                    verifiable=bool(c.get("verifiable", False)) if isinstance(c, dict) else False,
                    source=c.get("source") if isinstance(c, dict) else None,
                    # Mark as verified if a tool result supports this verifiable claim
                    verified=bool(c.get("verified", False)) or (bool(c.get("verifiable")) and bool(verified_tools))
                    if isinstance(c, dict) else False,
                )
                for c in (data.get("key_claims") or [])
            ]

            conf = data.get("confidence")
            if conf is not None:
                try:
                    conf = max(0.0, min(1.0, float(conf)))
                except (TypeError, ValueError):
                    conf = None

            return AgentOpinion(
                model_id=route.id,
                display_name=route.display_name,
                provider=route.provider,
                role=role,
                status="completed",
                content=content,
                answer_summary=str(data.get("answer_summary") or "") or None,
                confidence=conf,
                confidence_rationale=str(data.get("confidence_rationale") or "") or None,
                key_claims=claims,
                uncertainties=list(data.get("uncertainties") or []),
                tool_results=tool_results,
                structured_output_parsed=True,
                latency_ms=latency_ms,
                usage=usage,
            )
        except Exception:
            pass

    # Fallback: preserve prose, no structured fields
    return AgentOpinion(
        model_id=route.id,
        display_name=route.display_name,
        provider=route.provider,
        role=role,
        status="parse_failed",
        content=content,
        confidence=0.5,
        tool_results=tool_results,
        structured_output_parsed=False,
        latency_ms=latency_ms,
        usage=usage,
    )


# ---------------------------------------------------------------------------
# Stage 2 parsing helpers
# ---------------------------------------------------------------------------

def _parse_batch_critique(
    reviewer: AgentOpinion,
    critique_role: str,
    targets: list[AgentOpinion],
    anonymized_map: dict[str, str],
    content: str,
    latency_ms: int | None,
) -> list[CouncilCritique]:
    """Parse a batch critique response (reviewer scores all targets at once)."""
    label_for = {mid: label for label, mid in anonymized_map.items()}

    try:
        data = json.loads(_extract_json(content))
        reviews = data.get("reviews") or {}
    except Exception:
        # Full parse failure: mark all targets as parse_failed
        return [
            CouncilCritique(
                reviewer_model_id=reviewer.model_id,
                reviewer_display_name=reviewer.display_name,
                reviewer_critique_role=critique_role,
                target_model_id=t.model_id,
                target_display_name=t.display_name,
                status="parse_failed",
                anonymized_map=anonymized_map,
                content=content,
                latency_ms=latency_ms,
            )
            for t in targets
        ]

    result: list[CouncilCritique] = []
    for target in targets:
        label = label_for.get(target.model_id, target.model_id)
        review = reviews.get(label) or {}
        if not review:
            result.append(CouncilCritique(
                reviewer_model_id=reviewer.model_id,
                reviewer_display_name=reviewer.display_name,
                reviewer_critique_role=critique_role,
                target_model_id=target.model_id,
                target_display_name=target.display_name,
                status="parse_failed",
                anonymized_map=anonymized_map,
                content=content,
                latency_ms=latency_ms,
            ))
            continue

        def _score(key: str) -> float | None:
            v = review.get(key)
            try:
                return max(0.0, min(1.0, float(v))) if v is not None else None
            except (TypeError, ValueError):
                return None

        result.append(CouncilCritique(
            reviewer_model_id=reviewer.model_id,
            reviewer_display_name=reviewer.display_name,
            reviewer_critique_role=critique_role,
            target_model_id=target.model_id,
            target_display_name=target.display_name,
            status="completed",
            anonymized_map=anonymized_map,
            factual_accuracy_score=_score("factual_accuracy_score"),
            logical_validity_score=_score("logical_validity_score"),
            completeness_score=_score("completeness_score"),
            calibration_score=_score("calibration_score"),
            overall_rank=int(review["overall_rank"]) if "overall_rank" in review else None,
            strengths=list(review.get("strengths") or []),
            weaknesses=list(review.get("weaknesses") or []),
            corrective_additions=list(review.get("corrective_additions") or []),
            content=content,
            latency_ms=latency_ms,
        ))
    return result


# ---------------------------------------------------------------------------
# Stage 4 parsing helpers
# ---------------------------------------------------------------------------

def _synthesis_system() -> str:
    return """\
You are the elected Synthesizer in Model Council.

Return ONLY valid JSON:
{
  "direct_answer": "clear answer to the query",
  "consensus_points": ["points all/most models agreed on"],
  "dissent_points": ["where models disagreed and why"],
  "unresolved_conflicts": ["what remains genuinely uncertain or contested"],
  "confidence_grade": "A|B|C|D|F",
  "confidence_grade_rationale": "one sentence",
  "recommended_next_checks": ["specific actionable verification steps"],
  "provenance_map": {"claim text": ["model_id_1", "model_id_2"]}
}

Rule: Truth beats majority vote. If a minority view is better supported by evidence, say so.
Do not suppress dissent behind false consensus."""


def _synthesis_prompt(
    prompt: str,
    plan: OrchestrationPlan,
    opinions: list[AgentOpinion],
    critiques: list[CouncilCritique],
    election: LeaderElection,
) -> str:
    opinion_block = "\n\n".join(
        f"### {o.display_name} (role: {o.role}, status: {o.status})\n"
        f"Content: {o.content[:1500]}\n"
        f"Confidence: {o.confidence}\n"
        f"Summary: {o.answer_summary or 'N/A'}"
        for o in opinions
    )
    critique_block = "\n".join(
        f"- {c.reviewer_display_name} [{c.reviewer_critique_role}] → {c.target_display_name}: "
        f"accuracy={c.factual_accuracy_score}, logic={c.logical_validity_score}, "
        f"rank={c.overall_rank}; flags={c.corrective_additions}"
        for c in critiques
        if c.status == "completed"
    ) or "No critiques available."

    return f"""Original query:
{prompt}

You were elected leader: {election.rationale}

Election scores:
{json.dumps(election.score_breakdown, indent=2)}

First opinions:
{opinion_block}

Critiques:
{critique_block}
"""


def _parse_synthesis(
    route: ModelRoute, content: str, latency_ms: int | None, usage
) -> CouncilSynthesis:
    try:
        data = json.loads(_extract_json(content))
        grade = data.get("confidence_grade")
        if grade not in ("A", "B", "C", "D", "F"):
            grade = None
        return CouncilSynthesis(
            leader_model_id=route.id,
            leader_display_name=route.display_name,
            status="completed",
            direct_answer=str(data.get("direct_answer") or ""),
            consensus_points=list(data.get("consensus_points") or []),
            dissent_points=list(data.get("dissent_points") or []),
            unresolved_conflicts=list(data.get("unresolved_conflicts") or []),
            confidence_grade=grade,
            confidence_grade_rationale=str(data.get("confidence_grade_rationale") or "") or None,
            recommended_next_checks=list(data.get("recommended_next_checks") or []),
            raw_content=content,
            provenance_map=dict(data.get("provenance_map") or {}),
            latency_ms=latency_ms,
            usage=usage,
        )
    except Exception:
        return CouncilSynthesis(
            leader_model_id=route.id,
            leader_display_name=route.display_name,
            status="completed",
            direct_answer=content,
            raw_content=content,
            latency_ms=latency_ms,
            usage=usage,
        )


def _extract_json(content: str) -> str:
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found")
    return match.group(0)


def _sum_cost(items: list) -> float | None:
    costs = [
        item.usage.cost
        for item in items
        if getattr(item, "usage", None) and item.usage and item.usage.cost is not None
    ]
    return round(sum(costs), 6) if costs else None
