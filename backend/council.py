from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from uuid import uuid4

from backend.election import elect_leader
from backend.orchestrator import classify_query
from backend.providers import ProviderAdapter
from backend.roles import build_critique_prompt, build_system_prompt, critique_roles
from backend.schemas import (
    AgentOpinion,
    ChatMessage,
    Claim,
    CouncilCritique,
    CouncilRequest,
    CouncilRun,
    CouncilSynthesis,
    CritiqueScore,
    LeaderElection,
    ModelRoute,
    OrchestrationPlan,
    ProvenanceEntry,
    SynthesisValidation,
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

    async def run(self, request: CouncilRequest, run_id: str | None = None, stream: CouncilEventStream | None = None) -> CouncilRun:
        started = time.perf_counter()
        created_at = datetime.now(timezone.utc)
        if len(set(request.selected_model_ids)) != len(request.selected_model_ids):
            raise ValueError("Selected model IDs must be unique")
        selected = [self._route_or_raise(model_id) for model_id in request.selected_model_ids]
        plan = await self._stage0_orchestrate(request, selected)
        await self._emit(stream, "plan_ready", plan.model_dump())

        opinions = await self._stage1_first_opinions(plan, request, selected, stream)
        successful = [opinion for opinion in opinions if opinion.status in {"completed", "parse_failed"} and opinion.answer.strip()]
        if not successful:
            completed_at = datetime.now(timezone.utc)
            run = CouncilRun(
                id=run_id or str(uuid4()),
                status="failed",
                orchestration_plan=plan,
                agent_opinions=opinions,
                council_critiques=[],
                created_at=created_at,
                completed_at=completed_at,
                prompt=request.prompt,
                selected_models=selected,
                errors=[opinion.error or "Model failed" for opinion in opinions if opinion.status == "failed"],
                total_latency_ms=int((time.perf_counter() - started) * 1000),
                metadata={"pipeline": "model-council", "failure": "all_stage1_failed"},
            )
            self.store.save(run)
            await self._emit(stream, "run_complete", run.model_dump())
            return run

        critiques = await self._stage2_critique(successful, stream) if len(successful) >= 2 else []
        election = elect_leader(successful, critiques)
        await self._emit(stream, "leader_elected", election.model_dump())
        synthesis = await self._stage4_synthesize(election, plan, opinions, critiques, request)
        if synthesis.status == "failed" and self.synthesis_retry_on_failure and election.validator_model_id:
            retry_election = election.model_copy(
                update={
                    "leader_model_id": election.validator_model_id,
                    "leader_display_name": election.validator_display_name or election.validator_model_id,
                }
            )
            synthesis = await self._stage4_synthesize(retry_election, plan, opinions, critiques, request)
        await self._emit(stream, "synthesis_ready", synthesis.model_dump())
        validation = await self._stage5_validate(election, synthesis, opinions, critiques, request.prompt)
        await self._emit(stream, "validation_result", validation.model_dump())
        provenance = self._build_provenance_tree(synthesis, opinions, critiques)
        confidence_grade = synthesis.confidence_grade or self._compute_final_grade(synthesis, validation)
        errors = [
            item.error
            for item in [*opinions, *critiques, synthesis, validation]
            if getattr(item, "error", None)
        ]
        status = "completed"
        if synthesis.status == "failed":
            status = "failed"
        elif validation.status in {"flagged", "approved_with_caveats", "failed"}:
            status = "approved_with_caveats"
        elif errors:
            status = "partial_failed"

        completed_at = datetime.now(timezone.utc)
        run = CouncilRun(
            id=run_id or str(uuid4()),
            status=status,
            orchestration_plan=plan,
            agent_opinions=opinions,
            council_critiques=critiques,
            leader_election=election,
            synthesis=synthesis,
            validation=validation,
            provenance_tree=provenance,
            confidence_grade=confidence_grade,
            created_at=created_at,
            completed_at=completed_at,
            prompt=request.prompt,
            selected_models=selected,
            errors=[error for error in errors if error],
            total_latency_ms=int((time.perf_counter() - started) * 1000),
            total_tokens=sum((opinion.usage.total_tokens or 0) for opinion in opinions if opinion.usage),
            metadata={"pipeline": "model-council", "successful_first_opinions": len(successful)},
        )
        self.store.save(run)
        await self._emit(stream, "run_complete", run.model_dump())
        return run

    async def _stage0_orchestrate(self, request: CouncilRequest, selected: list[ModelRoute]) -> OrchestrationPlan:
        orchestrator_route = self.routes.get(self.orchestrator_model_id)
        adapter = self.adapters.get(orchestrator_route.provider) if orchestrator_route else None
        return await classify_query(request.prompt, selected, orchestrator_route, adapter, self.tool_registry)

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
            )
            await self._emit(stream, "agent_opinion", opinion.model_dump())
            return opinion

        return await asyncio.gather(*(run_one(route) for route in selected))

    async def _stage1_single_opinion(
        self,
        route: ModelRoute,
        role: str,
        tools: list[str],
        plan: OrchestrationPlan,
        request: CouncilRequest,
    ) -> AgentOpinion:
        system = build_system_prompt(role, plan.query_type)
        if request.system_context:
            system = f"{system}\n\nUser-provided context:\n{request.system_context}"
        tool_note = (
            "\nAvailable tools: "
            f"{', '.join(tools) or 'none'}. "
            "If you need a tool, include a line like TOOL_CALL: calculator: 2+2 before your final JSON."
        )
        try:
            content, usage, latency_ms = await self.adapters[route.provider].complete(
                route,
                [ChatMessage(role="system", content=system), ChatMessage(role="user", content=request.prompt + tool_note)],
            )
            allowed_registry = {name: self.tool_registry[name] for name in tools if name in self.tool_registry}
            content_with_tools, tool_results = await inject_tool_results(content, allowed_registry)
            opinion = _parse_opinion(route, role, content_with_tools, latency_ms, usage)
            opinion.tool_results = tool_results
            if tool_results:
                verified = {result.tool_name for result in tool_results if result.success}
                for claim in opinion.key_claims:
                    claim.supporting_tool_results = list(verified)
                    if verified:
                        claim.verification_status = "partially_verified"
            return opinion
        except Exception as exc:
            return AgentOpinion(
                model_id=route.id,
                display_name=route.display_name,
                provider=route.provider,
                role=role,
                status="failed",
                error=str(exc),
            )

    async def _stage2_critique(self, opinions: list[AgentOpinion], stream: CouncilEventStream | None) -> list[CouncilCritique]:
        roles = critique_roles(len(opinions))

        async def review(reviewer: AgentOpinion, critique_role: str) -> list[CouncilCritique]:
            tasks = [
                self._stage2_single_critique(reviewer, critique_role, target)
                for target in opinions
                if target.model_id != reviewer.model_id
            ]
            results = await asyncio.gather(*tasks)
            for result in results:
                await self._emit(stream, "critique_scored", result.model_dump())
            return results

        nested = await asyncio.gather(*(review(opinion, roles[index].value) for index, opinion in enumerate(opinions)))
        return [item for group in nested for item in group]

    async def _stage2_single_critique(
        self,
        reviewer: AgentOpinion,
        critique_role: str,
        target: AgentOpinion,
    ) -> CouncilCritique:
        route = self._route_or_raise(reviewer.model_id)
        try:
            content, _, latency_ms = await self.adapters[route.provider].complete(
                route,
                [
                    ChatMessage(role="system", content="You are a Model Council critique agent. Return only JSON."),
                    ChatMessage(role="user", content=build_critique_prompt(critique_role, target.display_name, target.answer)),
                ],
            )
            return _parse_critique(reviewer, target, critique_role, content, latency_ms)
        except Exception as exc:
            return CouncilCritique(
                reviewer_model_id=reviewer.model_id,
                reviewer_display_name=reviewer.display_name,
                target_model_id=target.model_id,
                target_display_name=target.display_name,
                critique_role=critique_role,
                status="failed",
                error=str(exc),
            )

    async def _stage4_synthesize(
        self,
        election: LeaderElection,
        plan: OrchestrationPlan,
        opinions: list[AgentOpinion],
        critiques: list[CouncilCritique],
        request: CouncilRequest,
    ) -> CouncilSynthesis:
        leader = self._route_or_raise(election.leader_model_id)
        try:
            content, _, latency_ms = await self.adapters[leader.provider].complete(
                leader,
                [
                    ChatMessage(role="system", content=_synthesis_system()),
                    ChatMessage(role="user", content=_synthesis_prompt(request.prompt, plan, opinions, critiques, election)),
                ],
            )
            return _parse_synthesis(leader, content, latency_ms)
        except Exception as exc:
            return CouncilSynthesis(
                leader_model_id=leader.id,
                leader_display_name=leader.display_name,
                status="failed",
                error=str(exc),
            )

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
        validator_id = election.validator_model_id or election.leader_model_id
        validator = self._route_or_raise(validator_id)
        try:
            content, _, latency_ms = await self.adapters[validator.provider].complete(
                validator,
                [
                    ChatMessage(role="system", content="You validate Model Council syntheses. Return only JSON."),
                    ChatMessage(role="user", content=build_validation_prompt(synthesis, critiques, original_query)),
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

    def _build_provenance_tree(
        self,
        synthesis: CouncilSynthesis,
        opinions: list[AgentOpinion],
        critiques: list[CouncilCritique],
    ) -> dict[str, ProvenanceEntry]:
        reviewers_by_target: dict[str, list[str]] = {}
        for critique in critiques:
            reviewers_by_target.setdefault(critique.target_model_id, []).append(critique.reviewer_model_id)
        entries: dict[str, ProvenanceEntry] = {}
        for opinion in opinions:
            for claim in opinion.key_claims:
                entries[claim.id] = ProvenanceEntry(
                    claim_id=claim.id,
                    claim=claim.text,
                    source_model_ids=[opinion.model_id],
                    reviewer_model_ids=reviewers_by_target.get(opinion.model_id, []),
                    verification_status=claim.verification_status,
                )
        return entries

    def _compute_final_grade(self, synthesis: CouncilSynthesis, validation: SynthesisValidation) -> str:
        if synthesis.status == "failed":
            return "F"
        if validation.status == "approved":
            return "A"
        if validation.status == "approved_with_caveats":
            return "B"
        if validation.status == "flagged":
            return "C"
        return "D"

    def _route_or_raise(self, model_id: str) -> ModelRoute:
        route = self.routes.get(model_id)
        if not route:
            raise ValueError(f"Unknown model route: {model_id}")
        return route

    async def _emit(self, stream: CouncilEventStream | None, event: str, payload: dict) -> None:
        if stream:
            await stream.emit(event, payload)


def _parse_opinion(route: ModelRoute, role: str, content: str, latency_ms: int | None, usage) -> AgentOpinion:
    try:
        data = json.loads(_extract_json(content))
        claims = [
            Claim(id=f"{route.id}-claim-{index + 1}", text=str(claim), source_model_id=route.id)
            for index, claim in enumerate(data.get("key_claims") or [])
        ]
        return AgentOpinion(
            model_id=route.id,
            display_name=route.display_name,
            provider=route.provider,
            role=role,
            status="completed",
            answer=str(data.get("answer") or ""),
            confidence=data.get("confidence"),
            key_claims=claims,
            assumptions=list(data.get("assumptions") or []),
            uncertainties=list(data.get("uncertainties") or []),
            raw_content=content,
            latency_ms=latency_ms,
            usage=usage,
        )
    except Exception:
        return AgentOpinion(
            model_id=route.id,
            display_name=route.display_name,
            provider=route.provider,
            role=role,
            status="parse_failed",
            answer=content,
            confidence=0.5,
            raw_content=content,
            latency_ms=latency_ms,
            usage=usage,
        )


def _parse_critique(
    reviewer: AgentOpinion,
    target: AgentOpinion,
    critique_role: str,
    content: str,
    latency_ms: int | None,
) -> CouncilCritique:
    try:
        data = json.loads(_extract_json(content))
        scores = CritiqueScore.model_validate(data.get("scores") or {})
        return CouncilCritique(
            reviewer_model_id=reviewer.model_id,
            reviewer_display_name=reviewer.display_name,
            target_model_id=target.model_id,
            target_display_name=target.display_name,
            critique_role=critique_role,
            status="completed",
            scores=scores,
            strengths=list(data.get("strengths") or []),
            weaknesses=list(data.get("weaknesses") or []),
            flags=list(data.get("flags") or []),
            raw_content=content,
            latency_ms=latency_ms,
        )
    except Exception:
        return CouncilCritique(
            reviewer_model_id=reviewer.model_id,
            reviewer_display_name=reviewer.display_name,
            target_model_id=target.model_id,
            target_display_name=target.display_name,
            critique_role=critique_role,
            status="parse_failed",
            raw_content=content,
            latency_ms=latency_ms,
        )


def _parse_synthesis(route: ModelRoute, content: str, latency_ms: int | None) -> CouncilSynthesis:
    try:
        data = json.loads(_extract_json(content))
        return CouncilSynthesis(
            leader_model_id=route.id,
            leader_display_name=route.display_name,
            status="completed",
            direct_answer=str(data.get("direct_answer") or data.get("answer") or ""),
            consensus=list(data.get("consensus") or []),
            dissent=list(data.get("dissent") or []),
            unresolved=list(data.get("unresolved") or []),
            confidence_grade=data.get("confidence_grade"),
            provenance=dict(data.get("provenance") or {}),
            raw_content=content,
            latency_ms=latency_ms,
        )
    except Exception:
        return CouncilSynthesis(
            leader_model_id=route.id,
            leader_display_name=route.display_name,
            status="completed",
            direct_answer=content,
            raw_content=content,
            latency_ms=latency_ms,
        )


def _synthesis_system() -> str:
    return """You are the elected Model Council leader.
Return only JSON:
{
  "direct_answer": "answer",
  "consensus": ["point"],
  "dissent": ["point"],
  "unresolved": ["point"],
  "confidence_grade": "A|B|C|D|F",
  "provenance": {"claim": ["model_id"]}
}"""


def _synthesis_prompt(
    prompt: str,
    plan: OrchestrationPlan,
    opinions: list[AgentOpinion],
    critiques: list[CouncilCritique],
    election: LeaderElection,
) -> str:
    opinion_block = "\n\n".join(
        f"### {opinion.display_name} ({opinion.role}, {opinion.status})\n{opinion.answer}"
        for opinion in opinions
    )
    critique_block = "\n".join(
        f"- {critique.reviewer_display_name} scored {critique.target_display_name}: "
        f"{critique.scores.average if critique.scores else 'n/a'}; flags={critique.flags}"
        for critique in critiques
    )
    return f"""Original query:
{prompt}

Orchestration plan:
{plan.model_dump_json()}

Election:
{election.model_dump_json()}

Opinions:
{opinion_block}

Critiques:
{critique_block or "No critiques available."}
"""


def _extract_json(content: str) -> str:
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found")
    return match.group(0)
