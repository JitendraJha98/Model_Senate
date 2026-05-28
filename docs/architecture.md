# Model Council — Advanced Agentic Pipeline Architecture
## Approach C: Hybrid Orchestration (Recommended)

> Replaces the current 3-stage "Model Senate" with a 6-stage adaptive deliberation protocol.
> The pipeline shape is determined at runtime based on the query. Leadership is earned, not assigned.
> Every claim in the final answer is traceable to its origin and verification status.

---

## Table of Contents

1. [System Philosophy](#1-system-philosophy)
2. [Full Pipeline Overview](#2-full-pipeline-overview)
3. [Stage 0 — Orchestrator](#3-stage-0--orchestrator)
4. [Stage 1 — Specialized Council First Opinions](#4-stage-1--specialized-council-first-opinions)
5. [Stage 2 — Cross-Model Critique Council](#5-stage-2--cross-model-critique-council)
6. [Stage 3 — Algorithmic Leader Election](#6-stage-3--algorithmic-leader-election)
7. [Stage 4 — Leader Synthesis](#7-stage-4--leader-synthesis)
8. [Stage 5 — Synthesis Validation](#8-stage-5--synthesis-validation)
9. [Stage 6 — Re-integration Agent (conditional)](#9-stage-6--re-integration-agent-conditional)
10. [Role System](#10-role-system)
11. [Tool System](#11-tool-system)
12. [Structured Output Protocol](#12-structured-output-protocol)
13. [Leader Election Algorithm](#13-leader-election-algorithm)
14. [Provenance Tree](#14-provenance-tree)
15. [Streaming Architecture](#15-streaming-architecture)
16. [All Pydantic Schemas](#16-all-pydantic-schemas)
17. [Backend Module Structure](#17-backend-module-structure)
18. [Frontend Component Structure](#18-frontend-component-structure)
19. [API Endpoints](#19-api-endpoints)
20. [Error Handling and Fault Tolerance](#20-error-handling-and-fault-tolerance)
21. [Testing Strategy](#21-testing-strategy)
22. [Backward Compatibility](#22-backward-compatibility)
23. [Configuration and Environment](#23-configuration-and-environment)
24. [Cost and Latency Model](#24-cost-and-latency-model)
25. [Migration Path from Model Senate](#25-migration-path-from-model-senate)

---

## 1. System Philosophy

### What Changed and Why

The original Model Senate is a **batch processor**: three fixed stages, one pass, no adaptation, pre-designated leader, no tool access, no structured output, and no quality gate on the synthesis. Every query is treated identically regardless of type or complexity.

The Model Council is an **adaptive deliberation protocol**:

- The pipeline shape is determined at runtime by the query — a factual question gets Fact Verifiers, a code question gets Code Verifiers, an ethics question gets Steelmans and Challengers.
- Roles are not permanently assigned to models — the orchestrator assigns the optimal role combination for each specific query.
- Leadership is earned algorithmically after reviewing each model's performance in Stages 1 and 2 — not pre-designated by the user.
- Every agent may use tools appropriate to their role — Fact Verifiers call web search, Code Verifiers run a REPL.
- All agent output is structured (not just freeform prose), enabling precise multi-dimensional scoring in Stage 2.
- A Validator model guards the exit before the final answer is returned.
- Real-time SSE streaming lets the user watch the council deliberate live rather than waiting for a single blocking response.

### Core Invariants

These rules hold across all runs:

1. One model failing at any stage does not abort the run.
2. Leadership is always determined by performance, never by user pre-selection.
3. The final answer must include a provenance trace for every major claim.
4. Tool failures do not abort the run — they mark claims as unverified.
5. The old `/api/senate/*` endpoints remain live. Nothing is deleted.
6. Pydantic schema validation is the contract between every stage — invalid output from one stage cannot propagate to the next.
7. Confidence grades are always computed algorithmically, never by self-report alone.

---

## 2. Full Pipeline Overview

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ STAGE 0 — ORCHESTRATOR                                          │
│  • Schema-constrained LLM call                                  │
│  • Classifies query type                                        │
│  • Decomposes multi-part queries into sub-questions             │
│  • Assigns roles to each selected model                         │
│  • Assigns tools to each role                                   │
│  • Emits: OrchestrationPlan                                     │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      │  (if decomposed: each sub-question runs Stages 1–5 in parallel)
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│ STAGE 1 — SPECIALIZED COUNCIL (parallel asyncio.gather)         │
│  • Each model receives its assigned role system prompt          │
│  • Role-appropriate tools are available                         │
│  • Structured output: answer + confidence + key_claims +        │
│    uncertainties + tool_results                                 │
│  • Emits: AgentOpinion[] (one per model)                        │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│ STAGE 2 — CROSS-MODEL CRITIQUE (parallel asyncio.gather)        │
│  • Each successful model assigned a critique role               │
│  • Reviews OTHER models' structured output                      │
│  • Multi-dimensional scoring: accuracy, logic, completeness,    │
│    calibration                                                  │
│  • Emits: CouncilCritique[] (reviewer × target matrix)          │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│ STAGE 3 — LEADER ELECTION (pure computation, no LLM call)       │
│  • Weighted score: rank + calibration + tool verification ratio │
│  • Winner is elected as Synthesizer                             │
│  • Runner-up becomes Stage 5 Validator                          │
│  • Emits: LeaderElection                                        │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│ STAGE 4 — LEADER SYNTHESIS                                      │
│  • Elected leader receives full evidence package                │
│  • Produces: direct answer + consensus map + dissent map +      │
│    confidence grade (A–F) + provenance tags                     │
│  • Emits: CouncilSynthesis                                      │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│ STAGE 5 — SYNTHESIS VALIDATION                                  │
│  • Runner-up model reads synthesis                              │
│  • Checks: dissents addressed? claims verifiable? confidence    │
│    calibrated? no hallucinated citations?                       │
│  • Verdict: APPROVED or FLAGGED (addendum, not full re-run)     │
│  • Emits: SynthesisValidation                                   │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      │  (only if query was decomposed in Stage 0)
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│ STAGE 6 — RE-INTEGRATION AGENT (conditional)                    │
│  • Receives all sub-question CouncilRuns                        │
│  • Resolves cross-sub-answer contradictions                     │
│  • Assembles unified coherent final answer                      │
│  • Emits: final top-level CouncilRun                            │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
              CouncilRun (saved to disk, returned via API)
```

---

## 3. Stage 0 — Orchestrator

### Purpose

The Orchestrator is the intelligence layer that makes the pipeline adaptive. It runs a single schema-constrained LLM call and produces an `OrchestrationPlan`. This plan drives every subsequent stage.

### Why Schema-Constrained

A free-running LLM orchestrator can hallucinate a malformed plan. By using a strict JSON schema with Pydantic validation, the call either returns a valid plan or raises an error handled by the fallback. The LLM is not trusted to invent the schema — only to fill it in.

### What It Does

1. **Query Classification**: Determines the query type from a fixed taxonomy:
   - `factual` — has a ground-truth answer, verifiable with sources
   - `analytical` — requires reasoning, weighing evidence, drawing conclusions
   - `code` — involves writing, debugging, or explaining code / computation
   - `ethics` — involves value judgements, moral reasoning, competing principles
   - `creative` — open-ended, no single correct answer
   - `multi_part` — contains multiple distinct questions that benefit from independent treatment

2. **Decomposition** (only for `multi_part`): Breaks the query into 2–5 sub-questions. Each sub-question gets its own classification and runs Stages 1–5 independently.

3. **Role Assignment**: Based on query type, selects the optimal role for each selected model using the role mapping table (see Section 10). If N models are selected and the optimal combination requires fewer roles, roles are duplicated across models.

4. **Tool Assignment**: Determines which tools each role may invoke during Stage 1.

### Fallback

If the orchestrator LLM call fails or returns an invalid schema:
- Query type defaults to `analytical`
- No decomposition
- All models assigned `Independent Expert` role
- No tools assigned
- Run proceeds with `orchestration_status: "fallback"` in metadata

### System Prompt (Stage 0)

```
You are an orchestration agent for Model Council, a multi-model deliberation system.
Your job is to analyze the user's query and return a structured JSON orchestration plan.
Do not answer the query. Only produce the plan.

Return ONLY valid JSON matching the provided schema. No prose. No markdown. Raw JSON only.

Query type taxonomy:
- factual: has a ground-truth answer, verifiable with sources
- analytical: requires reasoning, weighing evidence, drawing conclusions
- code: involves writing, debugging, or explaining code or computation
- ethics: involves value judgements, moral reasoning, competing principles
- creative: open-ended, no single correct answer
- multi_part: contains multiple distinct questions benefiting from independent treatment
```

### User Prompt Template (Stage 0)

```
Query: {prompt}

Available models: {model_ids_list}

Return an OrchestrationPlan JSON object with:
- query_type: one of [factual, analytical, code, ethics, creative, multi_part]
- is_multi_part: boolean
- sub_questions: list of strings (empty if not multi_part, 2-5 items if multi_part)
- role_assignments: dict mapping model_id to role name
- tool_assignments: dict mapping model_id to list of tool names
- decomposition_rationale: one sentence explaining why decomposition was/was not applied
```

---

## 4. Stage 1 — Specialized Council First Opinions

### Purpose

Each model answers the query (or sub-question) with a role-specific system prompt and access to its assigned tools. Outputs are structured — not just prose.

### Parallelism

All models run concurrently via `asyncio.gather`. One model failing does not block others.

### Role-Specific System Prompts

Each role gets a distinct system prompt built by `roles.py::build_system_prompt(role, query_type)`. Examples:

**Independent Expert:**
```
You are an expert council member in Model Council.
Answer the query fully and independently. You have not seen other models' answers.
Be precise. Calibrate your confidence explicitly — state what you are certain of and what you are not.
Name every assumption you are making. If the answer is genuinely uncertain, say so with specificity.
```

**Devil's Advocate:**
```
You are the Devil's Advocate in Model Council.
Your role is to surface the strongest counterargument to the expected or conventional answer.
Start by identifying what the conventional answer is, then argue forcefully against it.
Do not be contrarian for its own sake — find the genuinely strongest opposing case.
You are not trying to be right. You are trying to make the council think harder.
```

**Fact Verifier:**
```
You are the Fact Verifier in Model Council.
For every factual claim in your answer, you must either cite a verifiable source or mark the claim as unverified.
Use your web search tool to check key claims before including them.
Report tool results explicitly. Flag any claim you could not verify.
```

**Code Verifier:**
```
You are the Code Verifier in Model Council.
For any code or computation in your answer, run it using your code execution tool before presenting it.
Report the actual output. Do not claim code works without running it.
If execution reveals an error, fix it and re-run. Report the final working version only.
```

**Steelman:**
```
You are the Steelman agent in Model Council.
Your role is to identify the 2–3 major competing views on this question and build the strongest,
most charitable version of each. Do not argue for one view over another.
Make each view as compelling as possible. A reader should feel that each view is reasonable.
```

### Structured Output Format

Each agent is instructed to end its response with a `COUNCIL_OUTPUT:` JSON block:

```json
COUNCIL_OUTPUT:
{
  "answer_summary": "one sentence summary of the answer",
  "confidence": 0.85,
  "confidence_rationale": "why this confidence level",
  "key_claims": [
    {"text": "claim text", "verifiable": true, "source": "URL or null", "verified": false},
    {"text": "claim text", "verifiable": false, "source": null, "verified": false}
  ],
  "uncertainties": ["list of things the model explicitly does not know"],
  "tool_results": [
    {"tool": "web_search", "query": "...", "result": "..."}
  ]
}
```

The backend parses this block after each completion. If parsing fails, the prose answer is preserved but structured fields are `null` — the run continues with degraded (but not absent) output.

---

## 5. Stage 2 — Cross-Model Critique Council

### Purpose

Each successful Stage 1 model reviews other models' outputs with a critique-role system prompt. Reviews are multi-dimensional — not just a ranking.

### Parallelism

All critique calls run concurrently. A critique failure marks that reviewer's output as `failed` but does not stop others.

### What Each Reviewer Receives

- The original query
- Each other model's full prose answer AND their `COUNCIL_OUTPUT` structured block
- Models are anonymized: "Agent A", "Agent B", etc. (de-anonymized after Stage 2 completes)
- Their assigned critique role

### Critique Roles

| Critique Role | Focus |
|---|---|
| **Challenger** | Identify factual errors, unsupported claims, logical fallacies |
| **Steelman Reviewer** | Find what each answer got most right; build its strongest case |
| **Calibration Auditor** | Compare stated confidence against actual accuracy of claims |

The orchestrator assigns critique roles based on how many models are reviewing. With 3 reviewers: one Challenger, one Steelman, one Calibration Auditor. With 4+: duplicate the most valuable role for query type.

### Scoring

Each reviewer outputs scores for each target model:

```
factual_accuracy_score:   0.0–1.0  (are the claims correct?)
logical_validity_score:   0.0–1.0  (is the reasoning sound?)
completeness_score:       0.0–1.0  (was anything important missed?)
calibration_score:        0.0–1.0  (did confidence match accuracy?)
overall_rank:             1–N      (1 = best)
```

Scores and rankings are extracted via structured parsing. If the reviewer does not produce valid scores, the review is marked `parse_failed` and excluded from the election calculation.

### Anonymization Protocol

- Stage 2 uses "Agent A", "Agent B" labels (not model names) — same as the current system
- The label→model_id map is stored in `CouncilCritique.anonymized_map`
- De-anonymization happens in the election stage, not before

---

## 6. Stage 3 — Algorithmic Leader Election

### Purpose

Computes a weighted election score for each Stage 1 model using data from Stages 1 and 2. The winner becomes the Stage 4 Synthesizer. The runner-up becomes the Stage 5 Validator. No LLM call is made in this stage — it is pure Python computation.

### Election Score Formula

```python
def compute_election_score(
    model_id: str,
    opinions: list[AgentOpinion],
    critiques: list[CouncilCritique],
) -> float:
    # Weight 1: Peer ranking (40%)
    # Average rank across all reviewers, normalized to 0-1 (1.0 = best)
    ranks = [c.overall_rank for c in critiques if c.target_model_id == model_id]
    n_models = len(opinions)
    rank_score = (n_models - (mean(ranks) - 1)) / n_models if ranks else 0.0

    # Weight 2: Calibration (30%)
    # Correlation between model's stated confidence and accuracy scores it received
    stated_confidence = opinion_for(model_id).confidence  # from COUNCIL_OUTPUT
    received_accuracy = mean([c.factual_accuracy_score for c in critiques
                              if c.target_model_id == model_id])
    calibration_score = 1.0 - abs(stated_confidence - received_accuracy)

    # Weight 3: Tool verification ratio (30%)
    # Fraction of key_claims that were externally verified by tool results
    claims = opinion_for(model_id).key_claims
    verified = [c for c in claims if c.verified and c.verifiable]
    tool_ratio = len(verified) / len([c for c in claims if c.verifiable]) if claims else 0.0

    return 0.40 * rank_score + 0.30 * calibration_score + 0.30 * tool_ratio
```

### Tie-Breaking

If two models score within 0.02 of each other, the tie is broken by:
1. Higher `factual_accuracy_score` from critiques
2. If still tied: higher `first_place_votes` (same logic as current system)
3. If still tied: alphabetical model_id (deterministic)

### Election Result Object

```python
class LeaderElection:
    elected_model_id: str
    elected_display_name: str
    election_score: float
    runner_up_model_id: str
    runner_up_display_name: str
    runner_up_score: float
    all_scores: dict[str, float]      # model_id → score, for full UI display
    score_breakdown: dict[str, dict]  # model_id → {rank_score, calibration, tool_ratio}
    rationale: str                    # one-sentence plain-English explanation
    was_tie_broken: bool
```

This object is a first-class citizen in `CouncilRun` and fully visible in the UI. The user sees exactly why the elected leader beat the runner-up.

---

## 7. Stage 4 — Leader Synthesis

### Purpose

The elected leader model receives the complete evidence package and produces the final synthesized answer. The synthesis is structured: it must address consensus, dissent, uncertainty, and confidence grade explicitly.

### Evidence Package Sent to Leader

```
Original query: {prompt}

Your role: You are the elected Synthesizer. You were chosen because: {election.rationale}

All first opinions:
{for each model: role, answer, confidence, key_claims, tool_results}

All critiques:
{for each critique: reviewer role, scores for each model, strengths, weaknesses}

Aggregate election scores:
{table of model → score → breakdown}

SYNTHESIS INSTRUCTIONS:
Produce a final answer with exactly these sections:
1. DIRECT ANSWER — the answer to the query, clearly stated
2. CONSENSUS — what all (or most) models agreed on
3. DISSENT — where models disagreed and why (do not suppress minority views)
4. UNRESOLVED — what remains genuinely uncertain or contested
5. CONFIDENCE GRADE — A/B/C/D/F with one-sentence justification
6. NEXT CHECKS — specific steps a reader could take to verify the answer further

Rule: Truth beats majority vote. If a minority view is better supported by tool results or logic,
say so explicitly. Do not hide conflicts behind false consensus.

End with a PROVENANCE_TAGS JSON block mapping each major claim to its supporting models.
```

### Confidence Grade Rubric

| Grade | Meaning |
|---|---|
| A | High agreement + key claims tool-verified + calibrated confidence |
| B | Moderate agreement + some verification + minor unresolved dissent |
| C | Significant dissent or major claims unverified |
| D | Low agreement or most claims unverified or strong challenger position |
| F | Council could not converge; answer is highly speculative |

The grade is computed algorithmically first (from election scores and critique scores) and passed to the leader as a suggested grade. The leader may adjust by one grade with justification.

### Leader Synthesis Schema

```python
class CouncilSynthesis:
    leader_model_id: str
    leader_display_name: str
    status: Literal["completed", "failed"]
    direct_answer: str
    consensus_points: list[str]
    dissent_points: list[str]
    unresolved_conflicts: list[str]
    confidence_grade: Literal["A", "B", "C", "D", "F"]
    confidence_grade_rationale: str
    recommended_next_checks: list[str]
    raw_content: str                   # full prose synthesis
    provenance_map: dict[str, list[str]]  # claim_text → [model_ids]
    latency_ms: int
    usage: UsageMetadata
    error: str | None
```

---

## 8. Stage 5 — Synthesis Validation

### Purpose

The runner-up model reads the synthesis and checks it against a fixed quality rubric. This is the only quality gate before the answer is returned. It catches cases where the leader over-claimed, suppressed dissent, or hallucinated citations.

### What the Validator Checks

The validator is prompted to answer these questions explicitly (yes/no with justification):

1. Are all major dissent points from Stage 2 addressed in the synthesis?
2. Does the confidence grade match the evidence (not too high, not too low)?
3. Are any specific facts or citations present that were not in Stage 1 or Stage 2? (hallucination check)
4. Is the direct answer actually an answer to the original query?
5. Are the "NEXT CHECKS" actionable and specific?

### Verdict

- `APPROVED` — synthesis passes all checks. Run status: `completed`.
- `FLAGGED` — one or more checks failed. The validator appends a specific addendum to the synthesis explaining what was missing or incorrect. Run status: `approved_with_caveats`.

A `FLAGGED` verdict does not trigger a full re-run. It appends an addendum. This is a deliberate design choice to cap latency and cost.

### Validator Schema

```python
class SynthesisValidation:
    validator_model_id: str
    validator_display_name: str
    status: Literal["completed", "failed"]
    verdict: Literal["approved", "flagged"]
    checks: dict[str, bool]            # check_name → passed
    issues: list[str]                  # empty if approved
    addendum: str | None               # appended to synthesis if flagged
    latency_ms: int
```

---

## 9. Stage 6 — Re-integration Agent (Conditional)

### When It Runs

Only when `OrchestrationPlan.is_multi_part is True`. Each sub-question ran Stages 1–5 independently. Stage 6 assembles them.

### What It Does

A separate LLM call (using the original leader model or the highest-scoring model overall) receives:
- The original composite query
- All sub-question answers (with their grades and confidence)
- A list of any cross-sub-answer contradictions detected algorithmically

It produces a unified coherent answer that:
- Maintains internal consistency across sub-answers
- Notes where sub-questions had conflicting conclusions
- Inherits the lowest confidence grade of any sub-run

### Contradiction Detection

Before the LLM call, a lightweight check scans for contradictions:
- If sub-question A has confidence grade A and sub-question B has grade D and they touch overlapping claims, flag it
- Flagged contradictions are passed to the re-integration agent as explicit context

### Re-integration Output

```python
class ReintegrationOutput:
    model_id: str
    unified_answer: str
    sub_run_ids: list[str]
    contradictions_resolved: list[str]
    contradictions_unresolved: list[str]
    final_confidence_grade: Literal["A", "B", "C", "D", "F"]
    latency_ms: int
```

---

## 10. Role System

### The Seven Roles

| Role | Purpose | Stage | Tools |
|---|---|---|---|
| **Independent Expert** | Baseline high-quality independent answer | Stage 1 | None |
| **Devil's Advocate** | Strongest counterargument to the expected answer | Stage 1 | None |
| **Steelman** | Most charitable version of each competing view | Stage 1 | None |
| **Fact Verifier** | Ground-truth factual claims with sources | Stage 1 | WebSearch |
| **Code Verifier** | Test computational and code claims by running them | Stage 1 | CodeExecutor |
| **Domain Specialist** | Deep domain-specific expertise (domain set by orchestrator) | Stage 1 | Domain-specific |
| **Synthesizer** | Unify all evidence into a coherent final answer | Stage 4 | None |
| **Challenger** (critique) | Identify errors, unsupported claims, logical fallacies | Stage 2 | None |
| **Steelman Reviewer** (critique) | Find what each answer got most right | Stage 2 | None |
| **Calibration Auditor** (critique) | Compare stated confidence vs. accuracy | Stage 2 | None |

### Query Type → Role Assignment Table

| Query Type | 3 Models | 4 Models | 5 Models | 6+ Models |
|---|---|---|---|---|
| `factual` | Expert, FactVerifier, Devil | Expert, FactVerifier, Devil, Expert | Expert×2, FactVerifier, Devil, Expert | Expert×2, FactVerifier×2, Devil, Domain |
| `analytical` | Expert, Devil, Steelman | Expert×2, Devil, Steelman | Expert×2, Devil, Steelman×2 | Expert×2, Devil×2, Steelman×2 |
| `code` | Expert, CodeVerifier, Devil | Expert, CodeVerifier×2, Devil | Expert, CodeVerifier×2, Devil, Domain | Expert×2, CodeVerifier×2, Devil, Domain |
| `ethics` | Expert, Devil, Steelman | Expert, Devil, Steelman×2 | Expert, Devil×2, Steelman×2 | Expert×2, Devil×2, Steelman×2 |
| `creative` | Expert×2, Steelman | Expert×3, Steelman | Expert×3, Steelman×2 | Expert×4, Steelman×2 |
| `multi_part` | Decompose → assign per sub-question | same | same | same |

### Role Capabilities

Each role is implemented in `roles.py` as:

```python
class AgentRole(str, Enum):
    INDEPENDENT_EXPERT = "Independent Expert"
    DEVIL_ADVOCATE = "Devil's Advocate"
    STEELMAN = "Steelman"
    FACT_VERIFIER = "Fact Verifier"
    CODE_VERIFIER = "Code Verifier"
    DOMAIN_SPECIALIST = "Domain Specialist"
    SYNTHESIZER = "Synthesizer"

@dataclass
class RoleConfig:
    role: AgentRole
    system_prompt: str
    allowed_tools: list[ToolName]
    requires_structured_output: bool = True
    output_sections: list[str] = field(default_factory=list)
```

`build_system_prompt(role, query_type, domain=None)` in `roles.py` returns the full system prompt string. Query type is passed so prompts can be lightly specialized (e.g., Fact Verifier for a code question emphasizes documentation sources over general web search).

---

## 11. Tool System

### Tool Protocol

All tools implement a single async interface:

```python
class Tool(ABC):
    name: ToolName
    description: str

    @abstractmethod
    async def call(self, params: dict[str, Any]) -> ToolResult:
        raise NotImplementedError

@dataclass
class ToolResult:
    tool: ToolName
    params: dict[str, Any]
    result: str                  # stringified result
    success: bool
    error: str | None = None
    latency_ms: int = 0
```

### Available Tools

**WebSearch**
- Calls a configured search API (e.g., Tavily, Serper, Brave Search)
- Parameters: `{"query": str, "max_results": int}`
- Returns: top N results as title + URL + snippet
- Fallback: if API key missing, returns `ToolResult(success=False, error="WebSearch unavailable")`

**CodeExecutor**
- Runs Python code in a sandboxed subprocess
- Parameters: `{"code": str, "timeout_seconds": int}`
- Returns: stdout + stderr
- Security: runs in isolated subprocess with no network, no file system writes outside /tmp
- Fallback: if sandbox unavailable, marks claims as `unverifiable`

**Calculator**
- Evaluates mathematical expressions safely (uses `ast.literal_eval` approach, no `eval`)
- Parameters: `{"expression": str}`
- Returns: numeric result or parse error
- Used by Code Verifier for pure math without needing full code execution

### How Tools Are Invoked

Agents are prompted to embed tool calls in their response using a structured tag:

```
TOOL_CALL: {"tool": "web_search", "query": "Python vs JavaScript CPU benchmark 2024"}
TOOL_RESULT: [injected by backend after calling the tool]
```

The backend intercepts these tags mid-completion (or in a post-processing pass), calls the tool, and injects the result before the model continues. This is a simple injection pattern — not a full function-calling protocol — keeping it provider-agnostic.

### Tool Configuration

```python
class ToolConfig(BaseModel):
    web_search_enabled: bool = False
    web_search_provider: Literal["tavily", "serper", "brave"] = "tavily"
    web_search_api_key: str | None = None
    code_executor_enabled: bool = False
    code_executor_timeout_seconds: int = 10
    calculator_enabled: bool = True        # always on, no API key needed
```

---

## 12. Structured Output Protocol

### Why Structured Output

The current system uses freeform text with a `FINAL RANKING:` block parsed by regex. This is fragile and information-poor. The new system requires every agent to produce a `COUNCIL_OUTPUT:` JSON block after their prose. This enables:

- Precise multi-dimensional scoring in Stage 2 (reviewers score claims, not just prose quality)
- Algorithmic leader election using machine-readable confidence and verification data
- Provenance tagging at the claim level, not the sentence level
- Reliable automated calibration scoring

### Parse-Fail Handling

If a model's `COUNCIL_OUTPUT` block is missing or unparseable:
- The prose answer is preserved and used in all downstream stages
- All structured fields default to `null`
- The model is excluded from tool-verification scoring (treated as 0 tool-verified claims)
- The model is not excluded from peer review or election — it participates with degraded scoring

### Schema Enforcement

The `COUNCIL_OUTPUT` JSON is validated against a Pydantic model immediately after parsing. Any field that fails validation is set to its default null value. The run never aborts due to a structured output parse failure.

---

## 13. Leader Election Algorithm

### Full Implementation Detail

```python
def elect_leader(
    opinions: list[AgentOpinion],
    critiques: list[CouncilCritique],
) -> LeaderElection:
    scores = {}
    breakdowns = {}
    n_models = len(opinions)

    for opinion in opinions:
        mid = opinion.model_id

        # --- Rank Score (40%) ---
        relevant_critiques = [c for c in critiques if c.target_model_id == mid
                              and c.overall_rank is not None]
        if relevant_critiques:
            avg_rank = mean(c.overall_rank for c in relevant_critiques)
            # Normalize: rank 1 in a 4-model council → score 1.0; rank 4 → score 0.25
            rank_score = (n_models - avg_rank + 1) / n_models
        else:
            rank_score = 0.0

        # --- Calibration Score (30%) ---
        # How well did the model's confidence predict its actual accuracy?
        stated_confidence = opinion.confidence if opinion.confidence is not None else 0.5
        accuracy_scores = [c.factual_accuracy_score for c in critiques
                          if c.target_model_id == mid
                          and c.factual_accuracy_score is not None]
        avg_accuracy = mean(accuracy_scores) if accuracy_scores else 0.5
        # Perfect calibration = confidence matches accuracy exactly
        calibration_score = max(0.0, 1.0 - abs(stated_confidence - avg_accuracy))

        # --- Tool Verification Ratio (30%) ---
        verifiable_claims = [cl for cl in (opinion.key_claims or []) if cl.verifiable]
        verified_claims = [cl for cl in verifiable_claims if cl.verified]
        tool_ratio = len(verified_claims) / len(verifiable_claims) if verifiable_claims else 0.0

        final_score = 0.40 * rank_score + 0.30 * calibration_score + 0.30 * tool_ratio
        scores[mid] = final_score
        breakdowns[mid] = {
            "rank_score": round(rank_score, 3),
            "calibration_score": round(calibration_score, 3),
            "tool_verification_ratio": round(tool_ratio, 3),
            "final_score": round(final_score, 3),
        }

    # Sort descending by score
    sorted_models = sorted(opinions, key=lambda o: scores[o.model_id], reverse=True)
    winner = sorted_models[0]
    runner_up = sorted_models[1] if len(sorted_models) > 1 else winner

    # Check for tie (within 0.02)
    was_tie = abs(scores[winner.model_id] - scores[runner_up.model_id]) < 0.02

    return LeaderElection(
        elected_model_id=winner.model_id,
        elected_display_name=winner.display_name,
        election_score=scores[winner.model_id],
        runner_up_model_id=runner_up.model_id,
        runner_up_display_name=runner_up.display_name,
        runner_up_score=scores[runner_up.model_id],
        all_scores=scores,
        score_breakdown=breakdowns,
        rationale=build_election_rationale(winner, breakdowns[winner.model_id]),
        was_tie_broken=was_tie,
    )
```

---

## 14. Provenance Tree

### What It Stores

Every major claim in the final synthesis is tagged with its full evidence chain:

```python
@dataclass
class ProvenanceEntry:
    claim_text: str                          # the claim as it appears in the synthesis
    source_model_ids: list[str]              # which models made this claim
    validated_by: list[str]                  # reviewer model_ids that confirmed it
    challenged_by: list[str]                 # reviewer model_ids that challenged it
    tool_verified: bool                      # was it verified by a tool result?
    tool_result_summary: str | None          # snippet of the tool result that verified it
    confidence_contribution: float           # how much this claim contributed to the grade
    claim_confidence_grade: Literal["A","B","C","D","F"]
```

### How It Is Built

After Stage 4, the synthesis `PROVENANCE_TAGS` JSON block is parsed. The backend cross-references:
- Which models made each claim in Stage 1 (`key_claims`)
- Which reviewers validated or challenged each claim in Stage 2 (`strengths` / `weaknesses`)
- Whether any tool result verified the claim

The provenance tree is stored in `CouncilRun.provenance_tree` and returned in the API response. The frontend renders it as a click-to-expand panel on any sentence in the synthesis.

---

## 15. Streaming Architecture

### Design Choice

The current system blocks for the full pipeline duration (often 30–90 seconds) before returning anything. The new system returns a `run_id` immediately and streams stage completion events via SSE. The user watches the council deliberate in real time.

### Two-Call Pattern

```
POST /api/council/run
  Body: CouncilRequest
  Returns: {"run_id": "abc123"}   (immediate, ~50ms)

GET /api/council/run/{run_id}/stream
  Returns: SSE stream of events (one per stage output)

GET /api/council/run/{run_id}
  Returns: complete CouncilRun (available after stream completes)
```

### SSE Event Types and Payloads

```jsonc
// Stage 0 complete
{"event": "plan_ready", "data": {
  "query_type": "analytical",
  "is_multi_part": false,
  "role_assignments": {"model-id-1": "Independent Expert", "model-id-2": "Devil's Advocate"},
  "tool_assignments": {"model-id-1": [], "model-id-2": []},
  "sub_questions": []
}}

// Each Stage 1 opinion as it arrives (not waiting for all)
{"event": "agent_opinion", "data": {
  "model_id": "openrouter-gpt-5-2",
  "display_name": "GPT-5.2 via OpenRouter",
  "role": "Independent Expert",
  "status": "completed",
  "content": "...",
  "confidence": 0.82,
  "latency_ms": 4200
}}

// Each Stage 2 critique
{"event": "critique_scored", "data": {
  "reviewer_model_id": "...",
  "target_model_id": "...",
  "factual_accuracy_score": 0.85,
  "logical_validity_score": 0.90,
  "completeness_score": 0.70,
  "calibration_score": 0.80,
  "overall_rank": 1
}}

// Stage 3 election
{"event": "leader_elected", "data": {
  "elected_model_id": "...",
  "elected_display_name": "Gemini 3 Pro via OpenRouter",
  "election_score": 0.87,
  "runner_up_model_id": "...",
  "runner_up_score": 0.83,
  "rationale": "Highest peer ranking with 80% tool-verified claims"
}}

// Stage 4 synthesis complete
{"event": "synthesis_ready", "data": {
  "content": "...",
  "confidence_grade": "B",
  "consensus_points": ["..."],
  "dissent_points": ["..."]
}}

// Stage 5 validation
{"event": "validation_result", "data": {
  "verdict": "approved",
  "issues": []
}}

// Run complete
{"event": "run_complete", "data": {
  "run_id": "abc123",
  "status": "completed",
  "total_latency_ms": 28500
}}

// Error at any stage
{"event": "stage_error", "data": {
  "stage": "stage_1",
  "model_id": "...",
  "error": "Provider returned 429"
}}
```

### Implementation

```python
# streaming.py
import asyncio
from collections.abc import AsyncGenerator

class CouncilEventStream:
    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()

    async def emit(self, event_type: str, data: dict) -> None:
        await self._queue.put({"event": event_type, "data": data})

    async def events(self) -> AsyncGenerator[dict, None]:
        while True:
            event = await self._queue.get()
            yield event
            if event["event"] == "run_complete":
                break
```

`CouncilService` holds an `CouncilEventStream` per run, identified by `run_id`. The stream is stored in an in-memory dict keyed by `run_id`. When the SSE endpoint is hit, it reads from that stream. Runs are evicted from the in-memory dict after the stream closes.

---

## 16. All Pydantic Schemas

### New Schemas (schemas.py additions)

```python
# --- Stage 0 ---

class QueryType(str, Enum):
    FACTUAL = "factual"
    ANALYTICAL = "analytical"
    CODE = "code"
    ETHICS = "ethics"
    CREATIVE = "creative"
    MULTI_PART = "multi_part"

class SubQuestion(BaseModel):
    question: str
    query_type: QueryType

class OrchestrationPlan(BaseModel):
    query_type: QueryType
    is_multi_part: bool
    sub_questions: list[SubQuestion] = Field(default_factory=list)
    role_assignments: dict[str, str]          # model_id → role name
    tool_assignments: dict[str, list[str]]    # model_id → tool names
    decomposition_rationale: str
    orchestration_status: Literal["success", "fallback"] = "success"

# --- Stage 1 ---

class Claim(BaseModel):
    text: str
    verifiable: bool
    source: str | None = None
    verified: bool = False

class ToolResult(BaseModel):
    tool: str
    params: dict[str, Any]
    result: str
    success: bool
    error: str | None = None
    latency_ms: int = 0

class AgentOpinion(BaseModel):
    model_id: str
    display_name: str
    provider: ProviderName
    role: str
    status: Literal["completed", "failed"]
    content: str = ""
    answer_summary: str | None = None
    confidence: float | None = None
    confidence_rationale: str | None = None
    key_claims: list[Claim] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    structured_output_parsed: bool = False
    error: str | None = None
    latency_ms: int | None = None
    usage: UsageMetadata | None = None

# --- Stage 2 ---

class CritiqueRole(str, Enum):
    CHALLENGER = "Challenger"
    STEELMAN_REVIEWER = "Steelman Reviewer"
    CALIBRATION_AUDITOR = "Calibration Auditor"

class CouncilCritique(BaseModel):
    reviewer_model_id: str
    reviewer_display_name: str
    reviewer_critique_role: CritiqueRole
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

# --- Stage 3 ---

class LeaderElection(BaseModel):
    elected_model_id: str
    elected_display_name: str
    election_score: float
    runner_up_model_id: str
    runner_up_display_name: str
    runner_up_score: float
    all_scores: dict[str, float]
    score_breakdown: dict[str, dict[str, float]]
    rationale: str
    was_tie_broken: bool

# --- Stage 4 ---

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

# --- Stage 5 ---

class SynthesisValidation(BaseModel):
    validator_model_id: str
    validator_display_name: str
    status: Literal["completed", "failed"]
    verdict: Literal["approved", "flagged"] | None = None
    checks: dict[str, bool] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    addendum: str | None = None
    latency_ms: int | None = None

# --- Stage 6 ---

class ReintegrationOutput(BaseModel):
    model_id: str
    display_name: str
    status: Literal["completed", "failed"]
    unified_answer: str = ""
    sub_run_ids: list[str] = Field(default_factory=list)
    contradictions_resolved: list[str] = Field(default_factory=list)
    contradictions_unresolved: list[str] = Field(default_factory=list)
    final_confidence_grade: Literal["A", "B", "C", "D", "F"] | None = None
    latency_ms: int | None = None

# --- Provenance ---

class ProvenanceEntry(BaseModel):
    claim_text: str
    source_model_ids: list[str]
    validated_by: list[str] = Field(default_factory=list)
    challenged_by: list[str] = Field(default_factory=list)
    tool_verified: bool = False
    tool_result_summary: str | None = None
    claim_confidence_grade: Literal["A", "B", "C", "D", "F"] | None = None

# --- Top-Level ---

class CouncilRequest(BaseModel):
    prompt: str = Field(min_length=1)
    selected_model_ids: list[str] = Field(min_length=2)
    system_context: str | None = None
    # No leader_model_id — leader is elected algorithmically

class CouncilRun(BaseModel):
    id: str
    status: Literal["completed", "approved_with_caveats", "partial_failed", "failed"]
    orchestration_plan: OrchestrationPlan
    agent_opinions: list[AgentOpinion]
    council_critiques: list[CouncilCritique]
    leader_election: LeaderElection
    synthesis: CouncilSynthesis
    validation: SynthesisValidation
    reintegration: ReintegrationOutput | None = None   # populated if decomposed
    sub_runs: list["CouncilRun"] = Field(default_factory=list)  # if decomposed
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
```

---

## 17. Backend Module Structure

```
backend/
│
├── main.py              # FastAPI app, CORS, all endpoints (senate + council)
├── config.py            # Settings + ToolConfig + DEFAULT_ROUTES (unchanged)
├── providers.py         # Provider adapters (unchanged)
├── schemas.py           # All Pydantic models (extended with new schemas above)
├── storage.py           # ConversationStore extended to save/load CouncilRun
│
├── senate.py            # PRESERVED UNCHANGED — old pipeline still runs
│
├── orchestrator.py      # Stage 0: query classifier + decomposer + role assigner
│   # Functions:
│   #   classify_query(prompt, model_id, adapter) -> OrchestrationPlan
│   #   _fallback_plan(model_ids) -> OrchestrationPlan
│   #   _assign_roles(query_type, model_ids, n_models) -> dict[str, str]
│   #   _assign_tools(role_assignments, tool_config) -> dict[str, list[str]]
│
├── roles.py             # Role system
│   # Contents:
│   #   AgentRole(Enum)
│   #   CritiqueRole(Enum)
│   #   RoleConfig dataclass
│   #   ROLE_CONFIGS: dict[AgentRole, RoleConfig]
│   #   QUERY_ROLE_MAP: dict[QueryType, dict[int, list[AgentRole]]]
│   #   build_system_prompt(role, query_type, domain) -> str
│   #   build_critique_prompt(critique_role, opinions) -> str
│
├── tools.py             # Tool protocol + implementations
│   # Classes:
│   #   Tool(ABC)
│   #   ToolResult
│   #   WebSearchTool(Tool)
│   #   CodeExecutorTool(Tool)
│   #   CalculatorTool(Tool)
│   #   ToolRegistry: dict[str, Tool]
│   #   build_tool_registry(tool_config) -> ToolRegistry
│   #   inject_tool_results(content, tool_registry) -> tuple[str, list[ToolResult]]
│
├── council.py           # CouncilService: drives all 6 stages
│   # Class: CouncilService
│   #   __init__(routes, adapters, store, tool_registry)
│   #   async run(request) -> CouncilRun
│   #   async _stage0_orchestrate(request) -> OrchestrationPlan
│   #   async _stage1_first_opinions(plan, request) -> list[AgentOpinion]
│   #   async _stage1_single_opinion(route, role, tools, prompt, context) -> AgentOpinion
│   #   async _stage2_critique(plan, opinions) -> list[CouncilCritique]
│   #   async _stage2_single_critique(reviewer, critique_role, targets, opinions) -> list[CouncilCritique]
│   #   _stage3_elect_leader(opinions, critiques) -> LeaderElection
│   #   async _stage4_synthesize(election, plan, opinions, critiques, request) -> CouncilSynthesis
│   #   async _stage5_validate(election, synthesis, opinions, critiques) -> SynthesisValidation
│   #   async _stage6_reintegrate(sub_runs, original_prompt) -> ReintegrationOutput
│   #   _build_provenance_tree(synthesis, opinions, critiques) -> dict[str, ProvenanceEntry]
│   #   _compute_final_grade(synthesis, validation) -> str
│
├── election.py          # Leader election algorithm (pure functions, no I/O)
│   # Functions:
│   #   compute_election_score(model_id, opinions, critiques) -> float
│   #   elect_leader(opinions, critiques) -> LeaderElection
│   #   build_election_rationale(winner, breakdown) -> str
│
├── validator.py         # Stage 5: synthesis QA prompt builder + result parser
│   # Functions:
│   #   build_validation_prompt(synthesis, opinions, critiques, original_query) -> str
│   #   parse_validation_result(content, validator_route, latency_ms) -> SynthesisValidation
│
├── reintegrator.py      # Stage 6: sub-question assembly
│   # Functions:
│   #   detect_contradictions(sub_runs) -> list[str]
│   #   build_reintegration_prompt(sub_runs, original_query, contradictions) -> str
│   #   parse_reintegration_result(content, model_route) -> ReintegrationOutput
│
└── streaming.py         # SSE event emitter
    # Class: CouncilEventStream
    # Global: active_streams: dict[str, CouncilEventStream]
    # Functions:
    #   create_stream(run_id) -> CouncilEventStream
    #   get_stream(run_id) -> CouncilEventStream | None
    #   close_stream(run_id) -> None
```

---

## 18. Frontend Component Structure

```
frontend/src/
│
├── App.tsx              # Main app (extended: council workspace + senate workspace + history)
├── api.ts               # Typed fetch helpers (extended with council endpoints + SSE hook)
├── types.ts             # TypeScript interfaces (extended with all new schemas)
├── styles.css           # Global styles
│
└── components/
    │
    ├── council/
    │   ├── CouncilWorkspace.tsx          # Main council run view (replaces senate workspace for new runs)
    │   ├── PipelineProgress.tsx          # Live stage tracker: 6 stages with status indicators
    │   ├── OrchestrationPlanView.tsx     # Shows query type, role assignments, tool assignments
    │   ├── AgentCard.tsx                 # Individual model opinion card
    │   │                                 #   Props: opinion, role, confidence bar, tool results toggle
    │   ├── AgentGrid.tsx                 # Grid layout of all AgentCards
    │   ├── CritiqueMatrix.tsx            # Reviewer × Target grid with color-coded scores
    │   │                                 #   Columns: model names; Rows: reviewers; Cells: score heatmap
    │   ├── LeaderElectionView.tsx        # Horizontal bar chart of election scores
    │   │                                 #   Click a bar → see breakdown (rank, calibration, tool ratio)
    │   ├── SynthesisView.tsx             # Final answer display
    │   │                                 #   Sections: Direct Answer, Consensus, Dissent, Unresolved
    │   │                                 #   Each section has a collapsible provenance panel
    │   ├── ConfidenceGrade.tsx           # A–F badge with tooltip explanation
    │   ├── ProvenancePanel.tsx           # Click any claim → source models + reviewers + tool verification
    │   ├── ValidationBadge.tsx           # APPROVED / APPROVED WITH CAVEATS / FLAGGED badge + issues
    │   ├── DecompositionTree.tsx         # Sub-question breakdown (shown only if is_multi_part)
    │   │                                 #   Each sub-question is an expandable CouncilRun card
    │   └── ToolResultsDrawer.tsx         # Expandable panel showing all tool call results for a model
    │
    ├── senate/                           # Existing senate components (preserved unchanged)
    │   └── ...
    │
    └── shared/
        ├── StreamStatus.tsx              # Connection indicator for SSE stream
        └── ModelBadge.tsx               # Provider icon + model name chip
```

### Key Frontend Hooks

```typescript
// hooks/useCouncilStream.ts
// Manages SSE connection for a given run_id
// Maps incoming events to React state updates
// Exposes: { plan, opinions, critiques, election, synthesis, validation, isComplete }

function useCouncilStream(runId: string | null): CouncilStreamState {
  // Opens EventSource to /api/council/run/{runId}/stream
  // On each event: dispatches to local state reducer
  // On "run_complete": marks stream as done
  // On connection error: sets error state, does not auto-retry (user can refresh)
}
```

---

## 19. API Endpoints

### New Endpoints (Council)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/council/run` | Start a council run. Returns `{"run_id": "..."}` immediately. |
| `GET` | `/api/council/run/{run_id}/stream` | SSE stream of stage events for this run. |
| `GET` | `/api/council/run/{run_id}` | Retrieve complete `CouncilRun` after stream completes. |
| `GET` | `/api/council/runs` | List all past council runs (newest first). |

### Preserved Endpoints (Senate — unchanged)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Liveness check |
| `GET` | `/api/config` | Available models + defaults |
| `POST` | `/api/senate/run` | Execute old 3-stage pipeline |
| `GET` | `/api/conversations` | List past senate runs |
| `GET` | `/api/conversations/{run_id}` | Retrieve specific senate run |

### Request/Response Schemas

```typescript
// POST /api/council/run
// Request:
{
  prompt: string;             // required, min length 1
  selected_model_ids: string[]; // min 2 models
  system_context?: string;    // optional additional context
  // NOTE: no leader_model_id — leadership is elected
}
// Response:
{ run_id: string }

// GET /api/council/run/{run_id}
// Response: CouncilRun (full schema, see Section 16)

// GET /api/council/runs
// Response: CouncilRun[] (sorted newest-first, limited to last 100)
```

---

## 20. Error Handling and Fault Tolerance

### Failure Scenarios and Responses

| Stage | Failure | Response |
|---|---|---|
| Stage 0 (Orchestrator) | LLM call fails or returns invalid schema | Fallback plan: `analytical` type, all models as Independent Expert, no tools, `orchestration_status: "fallback"` |
| Stage 0 | Schema validation fails on returned JSON | Same fallback as above |
| Stage 1 | One model fails | Excluded from Stage 2 critique and election. Failure recorded in `agent_opinions` with `status: "failed"`. Run continues. |
| Stage 1 | All models fail | Run status `failed`. No further stages run. |
| Stage 1 | Structured output parse fails | Prose preserved. Structured fields null. Model participates with degraded scoring. |
| Stage 1 | Tool call fails (web search, code exec) | `ToolResult(success=False)`. Claims marked `unverified`. Model not excluded. |
| Stage 2 | Reviewer fails | That reviewer's critiques are absent. Election proceeds with reduced data. Run continues. |
| Stage 2 | Score parsing fails | Review marked `parse_failed`. Excluded from election scoring. |
| Stage 2 | Fewer than 2 successful Stage 1 models | Stage 2 skipped entirely. Election skipped. Best-effort synthesis from available model(s). |
| Stage 3 (Election) | All models have equal scores | Tie-broken deterministically (accuracy → first_place_votes → alphabetical model_id). |
| Stage 4 | Leader fails synthesis | Runner-up promoted to leader. Synthesis re-attempted once. If second attempt fails: `status: "partial_failed"`. |
| Stage 5 | Validator fails | Validation marked `status: "failed"`. Synthesis returned without validation. Run status: `approved_with_caveats`. |
| Stage 5 | Verdict: FLAGGED | Addendum appended to synthesis. Run status: `approved_with_caveats`. No re-run. |
| Stage 6 | Re-integration fails | Sub-run answers concatenated with a warning note. Final answer marked incomplete. |
| Any stage | Timeout (>90s per model call) | httpx client raises `ReadTimeout`. Handled as individual model failure. Run continues. |

### Status Definitions

| Status | Meaning |
|---|---|
| `completed` | All stages ran successfully. Validator approved synthesis. |
| `approved_with_caveats` | Run completed but validator flagged issues (addendum present), or validator itself failed. |
| `partial_failed` | Some models or stages failed, but a final answer was produced. |
| `failed` | No final answer produced (all Stage 1 models failed, or leader synthesis failed twice). |

---

## 21. Testing Strategy

### Unit Tests

`tests/test_orchestrator.py`
- Test classification for each query type with known prompts
- Test fallback plan when orchestrator call fails
- Test role assignment for every query_type × N_models combination
- Test tool assignment respects tool availability config

`tests/test_election.py`
- Test election score formula with known inputs
- Test tie-breaking logic in all three tiebreak scenarios
- Test edge cases: all models equal score, only one model, no critiques available

`tests/test_roles.py`
- Test `build_system_prompt` returns non-empty string for every role + query_type combination
- Test `QUERY_ROLE_MAP` covers all query types and model counts 2–8

`tests/test_tools.py`
- Test `CalculatorTool` with valid and invalid expressions
- Test `CodeExecutorTool` with timeout scenarios (mocked subprocess)
- Test `inject_tool_results` correctly parses `TOOL_CALL:` tags from content

`tests/test_election.py`
- Full formula verification with hand-calculated expected scores

### Integration Tests

`tests/test_council.py`
- Full pipeline run using `FakeAdapter` (same pattern as existing `test_senate.py`)
- `FakeAdapter` extended to handle role-specific prompts (matches on role keyword in system prompt)
- Assert `CouncilRun` schema is valid (Pydantic validates on construction)
- Assert stage sequence: opinions before critiques, critiques before election, etc.
- Assert that a failed model in Stage 1 is excluded from Stage 2 and election
- Assert fallback plan is used when orchestrator call fails

### Streaming Tests

`tests/test_streaming.py`
- Assert SSE event sequence is correct: `plan_ready` → `agent_opinion[]` → `critique_scored[]` → `leader_elected` → `synthesis_ready` → `validation_result` → `run_complete`
- Assert no events emitted after `run_complete`
- Assert `agent_opinion` events arrive before all opinions are complete (streaming, not batched)

### Regression Tests

`tests/test_senate.py` — unchanged. Old pipeline must continue to pass.

### Contract Tests

Every stage's output is validated by Pydantic before being passed to the next stage. A schema error in any stage is treated as a stage failure and triggers the fault tolerance path — not an unhandled exception.

---

## 22. Backward Compatibility

- `senate.py`, `SenateRun`, `SenateRequest`, `PeerReview`, `FinalSynthesis`, `ModelOutput` — all preserved exactly as-is.
- `/api/senate/run` and all `/api/conversations/*` endpoints — preserved.
- History view in frontend shows both `SenateRun` and `CouncilRun` records, distinguished by a type badge.
- Old `data/conversations/*.json` files remain readable. Storage module detects schema version by presence/absence of `orchestration_plan` field.

---

## 23. Configuration and Environment

### New Environment Variables

```
# Tools
TOOL_WEB_SEARCH_ENABLED=true
TOOL_WEB_SEARCH_PROVIDER=tavily          # tavily | serper | brave
TAVILY_API_KEY=...
SERPER_API_KEY=...
BRAVE_SEARCH_API_KEY=...

TOOL_CODE_EXECUTOR_ENABLED=true
TOOL_CODE_EXECUTOR_TIMEOUT_SECONDS=10

# Orchestrator
ORCHESTRATOR_MODEL_ID=openrouter-gpt-5-2  # which model to use for Stage 0
ORCHESTRATOR_PROVIDER=openrouter

# Council behavior
COUNCIL_MIN_MODELS=2                      # minimum models required (was 3 for senate)
COUNCIL_SYNTHESIS_RETRY_ON_FAILURE=true   # promote runner-up if leader fails
```

### Settings Extension

```python
class Settings(BaseSettings):
    # ... existing fields unchanged ...

    # Tool config
    tool_web_search_enabled: bool = False
    tool_web_search_provider: str = "tavily"
    tavily_api_key: str | None = None
    serper_api_key: str | None = None
    brave_search_api_key: str | None = None
    tool_code_executor_enabled: bool = False
    tool_code_executor_timeout_seconds: int = 10

    # Orchestrator config
    orchestrator_model_id: str = "openrouter-gpt-5-2"
    orchestrator_provider: str = "openrouter"

    # Council behavior
    council_min_models: int = 2
    council_synthesis_retry_on_failure: bool = True
```

---

## 24. Cost and Latency Model

### Token Cost Estimate (per council run, 4 models, typical analytical query)

| Stage | Calls | Tokens each | Total tokens |
|---|---|---|---|
| Stage 0: Orchestrator | 1 | ~500 in / ~300 out | ~800 |
| Stage 1: First Opinions | 4 | ~1,000 in / ~800 out | ~7,200 |
| Stage 2: Critiques | 4 | ~4,000 in / ~600 out | ~18,400 |
| Stage 4: Synthesis | 1 | ~8,000 in / ~1,200 out | ~9,200 |
| Stage 5: Validation | 1 | ~3,000 in / ~400 out | ~3,400 |
| **Total** | **11 calls** | | **~39,000 tokens** |

At $3/M tokens (blended OpenRouter rate), a typical run costs approximately **$0.12 per query**.

### Latency Estimate

| Stage | Parallelism | Estimated wall time |
|---|---|---|
| Stage 0 | Serial | 3–5 seconds |
| Stage 1 | All models parallel | 8–20 seconds (slowest model) |
| Stage 2 | All critics parallel | 10–25 seconds (slowest critic) |
| Stage 3 | Pure computation | <50ms |
| Stage 4 | Serial | 6–15 seconds |
| Stage 5 | Serial | 4–8 seconds |
| **Total** | | **31–73 seconds** |

With SSE streaming, the user sees Stage 1 opinions arriving at ~8–12 seconds and has substantial content to read before the pipeline completes.

---

## 25. Migration Path from Model Senate

### Phase 1 — Backend (no frontend changes)
1. Add new schemas to `schemas.py`
2. Implement `orchestrator.py`, `roles.py`, `tools.py` (without tool API keys — tools disabled by default)
3. Implement `election.py` and `validator.py`
4. Implement `council.py` (CouncilService)
5. Implement `streaming.py`
6. Add new endpoints to `main.py`
7. All existing tests must still pass

### Phase 2 — Frontend streaming
1. Implement `useCouncilStream.ts` hook
2. Add `CouncilWorkspace.tsx` with `PipelineProgress` and `AgentGrid`
3. Wire SSE stream to component state
4. Test with real models

### Phase 3 — Rich UI components
1. `CritiqueMatrix.tsx`
2. `LeaderElectionView.tsx` with score breakdown
3. `SynthesisView.tsx` with consensus/dissent sections
4. `ProvenancePanel.tsx`
5. `ValidationBadge.tsx`

### Phase 4 — Tool integration
1. Implement `WebSearchTool` with Tavily (lowest friction)
2. Implement `CodeExecutorTool` in sandboxed subprocess
3. Implement `CalculatorTool`
4. Test Fact Verifier and Code Verifier roles end-to-end

### Phase 5 — Query decomposition
1. Implement multi-part detection and sub-question splitting in `orchestrator.py`
2. Implement `reintegrator.py`
3. Implement `DecompositionTree.tsx` frontend component
4. Test with complex multi-part queries

---

*This document describes the complete design for Model Council — Approach C: Hybrid Orchestration. No code has been generated. This is the design spec. Implementation begins from the writing-plans phase.*
