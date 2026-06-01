export type ProviderName = "openrouter" | "openai" | "anthropic" | "google" | "xai";
export type QueryType = "factual" | "analytical" | "code" | "ethics" | "creative" | "multi_part";
export type ConfidenceGrade = "A" | "B" | "C" | "D" | "F";

export interface ModelRoute {
  id: string;
  provider: ProviderName;
  model: string;
  display_name: string;
  enabled: boolean;
  supports_streaming: boolean;
  missing_key: boolean;
}

export interface AppConfig {
  models: ModelRoute[];
  defaults: {
    selected_model_ids: string[];
    leader_model_id: string;
    min_models: number;
    council_selected_model_ids?: string[];
    council_min_models?: number;
  };
}

// ---------------------------------------------------------------------------
// Senate types (preserved)
// ---------------------------------------------------------------------------

export interface ModelOutput {
  model_id: string;
  display_name: string;
  provider: ProviderName;
  status: "completed" | "failed";
  content: string;
  error?: string;
  latency_ms?: number;
}

export interface RankingEntry {
  rank: number;
  response_label: string;
  model_id?: string;
  display_name?: string;
  reason?: string;
}

export interface AggregateRanking {
  model_id: string;
  display_name: string;
  average_rank: number;
  vote_count: number;
  first_place_votes: number;
  best_rank?: number;
  worst_rank?: number;
  confidence_score: number;
}

export interface PeerReview {
  reviewer_model_id: string;
  reviewer_display_name: string;
  status: "completed" | "failed";
  anonymized_map: Record<string, string>;
  parsed_ranking: RankingEntry[];
  content: string;
  error?: string;
  latency_ms?: number;
}

export interface FinalSynthesis {
  leader_model_id: string;
  leader_display_name: string;
  status: "completed" | "failed";
  content: string;
  error?: string;
  latency_ms?: number;
}

export interface SenateRun {
  id: string;
  status: "completed" | "partial_failed" | "failed";
  created_at: string;
  completed_at: string;
  prompt: string;
  selected_models: ModelRoute[];
  leader_model: ModelRoute;
  first_opinions: ModelOutput[];
  peer_reviews: PeerReview[];
  aggregate_rankings: AggregateRanking[];
  final_synthesis: FinalSynthesis;
  errors: string[];
  total_latency_ms: number;
  metadata: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Tool result
// ---------------------------------------------------------------------------

export interface ToolResult {
  tool: string;
  params: Record<string, unknown>;
  result: string;
  success: boolean;
  error?: string;
  latency_ms: number;
}

// ---------------------------------------------------------------------------
// Stage 0 — Orchestration
// ---------------------------------------------------------------------------

export interface SubQuestion {
  question: string;
  query_type: QueryType;
}

export interface OrchestrationPlan {
  query_type: QueryType;
  is_multi_part: boolean;
  sub_questions: SubQuestion[];
  role_assignments: Record<string, string>;
  tool_assignments: Record<string, string[]>;
  decomposition_rationale: string;
  orchestration_status: "success" | "fallback";
}

// ---------------------------------------------------------------------------
// Stage 1 — First Opinions
// ---------------------------------------------------------------------------

export interface Claim {
  text: string;
  verifiable: boolean;
  source?: string | null;
  verified: boolean;
}

export interface AgentOpinion {
  model_id: string;
  display_name: string;
  provider: ProviderName;
  role: string;
  status: "completed" | "failed" | "parse_failed";
  content: string;
  answer_summary?: string | null;
  confidence?: number | null;
  confidence_rationale?: string | null;
  key_claims: Claim[];
  uncertainties: string[];
  tool_results: ToolResult[];
  structured_output_parsed: boolean;
  error?: string | null;
  latency_ms?: number | null;
}

// ---------------------------------------------------------------------------
// Stage 2 — Cross-Model Critique
// ---------------------------------------------------------------------------

export interface CouncilCritique {
  reviewer_model_id: string;
  reviewer_display_name: string;
  reviewer_critique_role: string;
  target_model_id: string;
  target_display_name: string;
  status: "completed" | "failed" | "parse_failed";
  anonymized_map: Record<string, string>;
  factual_accuracy_score?: number | null;
  logical_validity_score?: number | null;
  completeness_score?: number | null;
  calibration_score?: number | null;
  overall_rank?: number | null;
  strengths: string[];
  weaknesses: string[];
  corrective_additions: string[];
  content: string;
  error?: string | null;
  latency_ms?: number | null;
}

// ---------------------------------------------------------------------------
// Stage 3 — Leader Election
// ---------------------------------------------------------------------------

export interface LeaderElection {
  elected_model_id: string;
  elected_display_name: string;
  election_score: number;
  runner_up_model_id: string;
  runner_up_display_name: string;
  runner_up_score: number;
  all_scores: Record<string, number>;
  score_breakdown: Record<string, Record<string, number>>;
  rationale: string;
  was_tie_broken: boolean;
}

// ---------------------------------------------------------------------------
// Stage 4 — Leader Synthesis
// ---------------------------------------------------------------------------

export interface CouncilSynthesis {
  leader_model_id: string;
  leader_display_name: string;
  status: "completed" | "failed";
  direct_answer: string;
  consensus_points: string[];
  dissent_points: string[];
  unresolved_conflicts: string[];
  confidence_grade?: ConfidenceGrade | null;
  confidence_grade_rationale?: string | null;
  recommended_next_checks: string[];
  raw_content: string;
  provenance_map: Record<string, string[]>;
  error?: string | null;
  latency_ms?: number | null;
}

// ---------------------------------------------------------------------------
// Stage 5 — Synthesis Validation
// ---------------------------------------------------------------------------

export interface SynthesisValidation {
  validator_model_id?: string | null;
  validator_display_name?: string | null;
  status: "completed" | "failed";
  verdict?: "approved" | "flagged" | null;
  checks: Record<string, boolean>;
  issues: string[];
  addendum?: string | null;
  error?: string | null;
  latency_ms?: number | null;
}

// ---------------------------------------------------------------------------
// Stage 6 — Re-integration (multi-part only)
// ---------------------------------------------------------------------------

export interface ReintegrationOutput {
  model_id: string;
  display_name: string;
  status: "completed" | "failed";
  unified_answer: string;
  sub_run_ids: string[];
  contradictions_resolved: string[];
  contradictions_unresolved: string[];
  final_confidence_grade?: ConfidenceGrade | null;
  error?: string | null;
  latency_ms?: number | null;
}

// ---------------------------------------------------------------------------
// Provenance
// ---------------------------------------------------------------------------

export interface ProvenanceEntry {
  claim_text: string;
  source_model_ids: string[];
  validated_by: string[];
  challenged_by: string[];
  tool_verified: boolean;
  tool_result_summary?: string | null;
  claim_confidence_grade?: ConfidenceGrade | null;
}

// ---------------------------------------------------------------------------
// Top-level Council run
// ---------------------------------------------------------------------------

export interface CouncilRun {
  id: string;
  status: "completed" | "approved_with_caveats" | "partial_failed" | "failed";
  orchestration_plan: OrchestrationPlan;
  agent_opinions: AgentOpinion[];
  council_critiques: CouncilCritique[];
  leader_election?: LeaderElection | null;
  synthesis?: CouncilSynthesis | null;
  validation?: SynthesisValidation | null;
  reintegration?: ReintegrationOutput | null;
  sub_runs: CouncilRun[];
  provenance_tree: Record<string, ProvenanceEntry>;
  confidence_grade?: ConfidenceGrade | null;
  created_at: string;
  completed_at: string;
  prompt: string;
  selected_models: ModelRoute[];
  errors: string[];
  total_latency_ms: number;
  total_tokens: number;
  total_cost_usd?: number | null;
  metadata: Record<string, unknown>;
}
