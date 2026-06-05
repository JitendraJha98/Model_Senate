from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ProviderName = Literal["openrouter", "openai", "anthropic", "google", "xai"]
RunStatus = Literal["completed", "approved_with_caveats", "partial_failed", "failed"]
QueryType = Literal["factual", "analytical", "code", "ethics", "creative", "multi_part"]


class ModelRoute(BaseModel):
    id: str
    provider: ProviderName
    model: str
    display_name: str
    enabled: bool = True
    supports_streaming: bool = False
    missing_key: bool = False


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class UsageMetadata(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost: float | None = None


# ---------------------------------------------------------------------------
# Senate schemas (preserved unchanged)
# ---------------------------------------------------------------------------

class SenateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    selected_model_ids: list[str] = Field(min_length=3)
    leader_model_id: str
    system_context: str | None = None


class RankingEntry(BaseModel):
    rank: int
    response_label: str
    model_id: str | None = None
    display_name: str | None = None
    reason: str | None = None


class AggregateRanking(BaseModel):
    model_id: str
    display_name: str
    average_rank: float
    vote_count: int
    first_place_votes: int = 0
    best_rank: int | None = None
    worst_rank: int | None = None
    confidence_score: float


class ModelOutput(BaseModel):
    model_id: str
    display_name: str
    provider: ProviderName
    status: Literal["completed", "failed"]
    content: str = ""
    error: str | None = None
    latency_ms: int | None = None
    usage: UsageMetadata | None = None


class PeerReview(BaseModel):
    reviewer_model_id: str
    reviewer_display_name: str
    status: Literal["completed", "failed"]
    anonymized_map: dict[str, str] = Field(default_factory=dict)
    parsed_ranking: list[RankingEntry] = Field(default_factory=list)
    content: str = ""
    error: str | None = None
    latency_ms: int | None = None


class FinalSynthesis(BaseModel):
    leader_model_id: str
    leader_display_name: str
    status: Literal["completed", "failed"]
    content: str = ""
    error: str | None = None
    latency_ms: int | None = None


class SenateRun(BaseModel):
    id: str
    status: RunStatus
    created_at: datetime
    completed_at: datetime
    prompt: str
    selected_models: list[ModelRoute]
    leader_model: ModelRoute
    first_opinions: list[ModelOutput]
    peer_reviews: list[PeerReview]
    aggregate_rankings: list[AggregateRanking] = Field(default_factory=list)
    final_synthesis: FinalSynthesis
    errors: list[str] = Field(default_factory=list)
    total_latency_ms: int
    total_tokens: int = 0
    total_cost_usd: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Council request
# ---------------------------------------------------------------------------

class CouncilRequest(BaseModel):
    prompt: str = Field(min_length=1)
    selected_model_ids: list[str] = Field(min_length=2)
    system_context: str | None = None


# ---------------------------------------------------------------------------
# Tool result (shared by Senate and Council)
# ---------------------------------------------------------------------------

class ToolResult(BaseModel):
    tool: str
    params: dict[str, Any] = Field(default_factory=dict)
    result: str = ""
    success: bool
    error: str | None = None
    latency_ms: int = 0


# ---------------------------------------------------------------------------
# Stage 0 — Orchestration
# ---------------------------------------------------------------------------

class SubQuestion(BaseModel):
    question: str
    query_type: QueryType


class OrchestrationPlan(BaseModel):
    query_type: QueryType
    is_multi_part: bool = False
    sub_questions: list[SubQuestion] = Field(default_factory=list)
    role_assignments: dict[str, str] = Field(default_factory=dict)
    tool_assignments: dict[str, list[str]] = Field(default_factory=dict)
    decomposition_rationale: str = ""
    orchestration_status: Literal["success", "fallback"] = "success"


# ---------------------------------------------------------------------------
# Stage 1 — First Opinions
# ---------------------------------------------------------------------------

class Claim(BaseModel):
    text: str
    verifiable: bool = False
    source: str | None = None
    verified: bool = False


class AgentOpinion(BaseModel):
    model_id: str
    display_name: str
    provider: ProviderName
    role: str
    status: Literal["completed", "failed", "parse_failed"]
    content: str = ""
    answer_summary: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    confidence_rationale: str | None = None
    key_claims: list[Claim] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    structured_output_parsed: bool = False
    error: str | None = None
    latency_ms: int | None = None
    usage: UsageMetadata | None = None


# ---------------------------------------------------------------------------
# Stage 2 — Cross-Model Critique
# ---------------------------------------------------------------------------

class CouncilCritique(BaseModel):
    reviewer_model_id: str
    reviewer_display_name: str
    reviewer_critique_role: str
    target_model_id: str
    target_display_name: str
    status: Literal["completed", "failed", "parse_failed"]
    anonymized_map: dict[str, str] = Field(default_factory=dict)
    factual_accuracy_score: float | None = None
    logical_validity_score: float | None = None
    completeness_score: float | None = None
    calibration_score: float | None = None
    overall_rank: int | None = None
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    corrective_additions: list[str] = Field(default_factory=list)
    content: str = ""
    error: str | None = None
    latency_ms: int | None = None


# ---------------------------------------------------------------------------
# Stage 3 — Leader Election
# ---------------------------------------------------------------------------

class LeaderElection(BaseModel):
    elected_model_id: str
    elected_display_name: str
    election_score: float
    runner_up_model_id: str
    runner_up_display_name: str
    runner_up_score: float
    all_scores: dict[str, float] = Field(default_factory=dict)
    score_breakdown: dict[str, dict[str, float]] = Field(default_factory=dict)
    rationale: str = ""
    was_tie_broken: bool = False


# ---------------------------------------------------------------------------
# Stage 4 — Leader Synthesis
# ---------------------------------------------------------------------------

class CouncilSynthesis(BaseModel):
    leader_model_id: str
    leader_display_name: str
    status: Literal["completed", "failed"]
    direct_answer: str = ""
    consensus_points: list[str] = Field(default_factory=list)
    dissent_points: list[str] = Field(default_factory=list)
    unresolved_conflicts: list[str] = Field(default_factory=list)
    confidence_grade: Literal["A", "B", "C", "D", "F"] | None = None
    confidence_grade_rationale: str | None = None
    recommended_next_checks: list[str] = Field(default_factory=list)
    raw_content: str = ""
    provenance_map: dict[str, list[str]] = Field(default_factory=dict)
    error: str | None = None
    latency_ms: int | None = None
    usage: UsageMetadata | None = None


# ---------------------------------------------------------------------------
# Stage 5 — Synthesis Validation
# ---------------------------------------------------------------------------

class SynthesisValidation(BaseModel):
    validator_model_id: str | None = None
    validator_display_name: str | None = None
    status: Literal["completed", "failed"]
    verdict: Literal["approved", "flagged"] | None = None
    checks: dict[str, bool] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    addendum: str | None = None
    error: str | None = None
    latency_ms: int | None = None


# ---------------------------------------------------------------------------
# Stage 6 — Re-integration (conditional, multi-part only)
# ---------------------------------------------------------------------------

class ReintegrationOutput(BaseModel):
    model_id: str = ""
    display_name: str = ""
    status: Literal["completed", "failed"]
    unified_answer: str = ""
    sub_run_ids: list[str] = Field(default_factory=list)
    contradictions_resolved: list[str] = Field(default_factory=list)
    contradictions_unresolved: list[str] = Field(default_factory=list)
    final_confidence_grade: Literal["A", "B", "C", "D", "F"] | None = None
    error: str | None = None
    latency_ms: int | None = None


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

class ProvenanceEntry(BaseModel):
    claim_text: str
    source_model_ids: list[str] = Field(default_factory=list)
    validated_by: list[str] = Field(default_factory=list)
    challenged_by: list[str] = Field(default_factory=list)
    tool_verified: bool = False
    tool_result_summary: str | None = None
    claim_confidence_grade: Literal["A", "B", "C", "D", "F"] | None = None


# ---------------------------------------------------------------------------
# Top-level Council run
# ---------------------------------------------------------------------------

class CouncilRun(BaseModel):
    id: str
    status: RunStatus
    orchestration_plan: OrchestrationPlan
    agent_opinions: list[AgentOpinion]
    council_critiques: list[CouncilCritique]
    leader_election: LeaderElection | None = None
    synthesis: CouncilSynthesis | None = None
    validation: SynthesisValidation | None = None
    reintegration: ReintegrationOutput | None = None
    sub_runs: list["CouncilRun"] = Field(default_factory=list)
    provenance_tree: dict[str, ProvenanceEntry] = Field(default_factory=dict)
    confidence_grade: Literal["A", "B", "C", "D", "F"] | None = None
    created_at: datetime
    completed_at: datetime
    prompt: str
    selected_models: list[ModelRoute]
    errors: list[str] = Field(default_factory=list)
    total_latency_ms: int
    total_tokens: int = 0
    total_cost_usd: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# API response
# ---------------------------------------------------------------------------

class AppConfigResponse(BaseModel):
    models: list[ModelRoute]
    defaults: dict[str, Any]
