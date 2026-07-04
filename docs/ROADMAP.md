# Model Council — Roadmap to the Best Open-Source LLM Council

> **Status:** Development plan. Approved for documentation; implementation to follow later.
> **Strategy:** Proof-first. Build the measurement substrate, then let data drive every
> quality/cost/UX change.

---

## 0. Executive Summary

Our **Council** pipeline already out-*designs* every public competitor — dynamic
leader **election** (not a fixed chairman), critique **scoring**, validation, multi-part
decomposition, provenance, confidence grades, and live SSE streaming. What we lack is
**proof**, **economics**, and **visibility**. This roadmap fixes all three, in
dependency order:

1. **Phase 0 — Foundational fixes** (honesty + unblock): reconcile docs vs code, finish
   cost tracking, make tools available to the harness/verifier.
2. **Phase 1 — KEYSTONE: Evaluation harness + Multi-round Debate.** A reproducible
   benchmark proving Council beats single models, self-consistency, and naive councils —
   shipped with one flagship answer-quality feature (debate) so there is a real gain to
   measure. **This is the thing that wins open source.**
3. **Phase 2 — Answer-quality depth:** adversarial tool-grounded verification,
   disagreement as a first-class output, claim-level citations, measured calibration.
4. **Phase 3 — Cost & speed:** prompt caching, reasoning-budget control, smart
   routing/tiering, early-exit on consensus, cost budgets.
5. **Phase 4 — Product & trust:** provenance visualization, in-app leaderboard,
   health/doctor, exports, public API, observability.

Every Phase 2–4 feature is **accepted only when a harness re-run shows the intended
accuracy/calibration gain at an acceptable cost delta.** That contract is what separates
us from "trust us, we're better."

---

## 1. Competitive Landscape (research summary)

| Project | Pipeline | Leader | Tools | Streaming | Proof/Evals | Caching | Notable |
|---|---|---|---|---|---|---|---|
| karpathy/llm-council | 3-stage (opinions → anon rank → chairman) | Fixed chairman | none | no | none | no | "99% vibe-coded weekend project, no intent to improve" |
| llmcouncil.ai / .so | Same 3-stage | Fixed chairman | none | partial | none | n/a | Commercial SaaS ($9–29/mo); Karpathy's design productized |
| gcpdev/llm-council-skill | 3-stage Claude skill | Claude synthesizes | none | no | none | no | Lightweight; Claude consults GPT + Gemini |
| Perplexity Model Council | 3 models → synthesizer | Synthesizer | web | yes | internal | n/a | Closed. Key idea: *make disagreement visible*; model strength varies by task |
| sherifkozman/the-llm-council | 5-stage (health → drafts → adversarial critique → synth → JSON-validate) | **No leader** (adversarial merge) | code-centric | — | **eval tooling** | **yes** | Most rigorous rival: thinking budgets, prompt caching, cost/latency profiles, secret redaction, `doctor` healthcheck |
| **OUR Council** | **5-stage + multi-part Stage 6** | **Dynamically elected (scored)** | calc/code/web | **yes (SSE)** | **none** | **no** | Most sophisticated *pipeline*; unproven; several features hidden/off |

**Reads:**
- karpathy / llmcouncil.ai / gcpdev = our **Senate** pipeline's level. We are already past them.
- **sherifkozman** is the only rival ahead of us *on engineering economics* (caching,
  reasoning budgets, eval tooling, doctor). That is our gap list for Phases 1 and 3.
- **Perplexity** contributes one product idea worth stealing: *surface disagreement
  explicitly and tell the user when an answer is "good enough."* → Phase 2 convergence map.

---

## 2. Where We Stand — Gap Analysis (code-grounded)

Verified against the codebase:

**Strengths (keep / showcase):** Council Stages 0–6 fully wired (`backend/council.py`);
LLM orchestrator + heuristic fallback (`backend/orchestrator.py`); 7 agent roles + 3
critique roles (`backend/roles.py`); scored leader election (`backend/election.py`);
5-point validation (`backend/validator.py`); multi-part reintegration
(`backend/reintegrator.py`); 5 provider adapters with retry + global semaphore
(`backend/providers.py`); live SSE (`backend/streaming.py`) rendered by the frontend
(`frontend/src/App.tsx`, `useCouncilStream.ts`).

**Gaps / debt to fix:**
| # | Gap | Evidence | Phase |
|---|---|---|---|
| G1 | Election weights doc≠code | `CLAUDE.md` says `(0.6,0.25,0.15)`; `election.py` uses `(0.40,0.30,0.30)` | 0 |
| G2 | Stale docs: web search "not implemented" but it is | `tools.py` has Tavily/Serper/Brave | 0 |
| G3 | No cost for Anthropic/Google | `providers.py` returns `cost=None` | 0 |
| G4 | Tools off by default, never used for grounding | `config.py` flags `False` | 0/2 |
| G5 | **No evaluation harness at all** | (absent) | **1** |
| G6 | Critique is single-pass; no debate/refinement | `council.py` `_stage2` → `_stage3` | **1** |
| G7 | No prompt caching | `providers.py` | 3 |
| G8 | No reasoning-budget control | `providers.py` / routes | 3 |
| G9 | Provenance built but never visualized | `council.py` builds it; UI omits | 4 |
| G10 | Multi-part rarely triggers; no per-subquestion timeout | `council.py` gather | 3/2 |

---

## 3. Strategy & Dependency Graph

```
                 ┌─────────────────────────────┐
   Phase 0 ──▶   │  Phase 1: EVAL HARNESS       │ ◀── flagship: multi-round DEBATE
  (unblock)      │  (the measurement substrate) │
                 └──────────────┬──────────────┘
                                │ every change measured here
            ┌───────────────────┼───────────────────┐
            ▼                    ▼                    ▼
     Phase 2 (depth)     Phase 3 (cost/speed)   Phase 4 (product/trust)
     verify, citations,  caching, routing,      provenance viz, leaderboard,
     calibration,        early-exit, budgets    doctor, exports, API
     disagreement map
```

Rationale: the harness is the only thing that turns "fancier pipeline" into
"provably better answers." Debate ships with it so the harness validates a real,
literature-backed feature on day one (Du et al., *Multiagent Debate*).

---

## 4. Phase 0 — Foundational Fixes

Small, surgical, no behavior risk. Ship first.

**0.1 Reconcile election weights (G1).** Decide canonical weights; update both
`backend/election.py` and `CLAUDE.md`. (Recommend keeping `(0.40,0.30,0.30)` — it
weights tool-grounding and calibration more, which the harness can later validate.)

**0.2 Fix stale docs (G2).** Correct `CLAUDE.md` tool/web-search descriptions to match
`backend/tools.py`.

**0.3 Complete cost tracking (G3).** Add per-provider price tables (USD per 1M
prompt/completion tokens) and compute `cost` for Anthropic + Google in
`backend/providers.py` from token counts. Needed for leaderboard cost columns.

**0.4 Tool availability for harness/verifier (G4).** Allow the eval harness and the
(Phase 2) verifier role to enable `web_search` / `code_executor` via an explicit param
without flipping the global user-facing default.

**Acceptance:** `uv run pytest` green; `CLAUDE.md` matches code; a Council run reports
non-null cost for every provider.

---

## 5. Phase 1 — KEYSTONE: Evaluation Harness + Multi-Round Debate

### 5A. Evaluation & Benchmark Harness

New package `backend/eval/`:

| File | Responsibility | Key API |
|---|---|---|
| `datasets.py` | Load curated benchmark subsets as JSONL | `load_suite(name) -> list[EvalItem]` |
| `scorers.py` | Score a prediction vs gold | `score(item, prediction) -> Score` |
| `baselines.py` | Run each configuration on one item | `run_config(cfg, item, adapters) -> Prediction` |
| `harness.py` | Drive config × suite, aggregate metrics | `run_eval(suites, configs, limit) -> EvalReport` |
| `report.py` | Render leaderboard + ablation tables | `write_report(report, out_dir)` |
| `metrics.py` | accuracy, win-rate, ECE, cost, latency | pure functions |
| `run.py` (`__main__`) | CLI entry | argparse |
| `data/*.jsonl` | Bundled curated fixtures | — |
| `calibration.json` | Fitted grade→probability map (written by harness) | — |

**Datasets (curated, bundled, reproducible):** exact sources so an implementer can
build the JSONL fixtures without guesswork — all permissively licensed (MIT/CC-BY/Apache):
- **Factual** — TruthfulQA (`truthful_qa`, Apache-2.0) generation/MC split + a SimpleQA
  (OpenAI, MIT) slice; ~100 short verifiable Q. Strongest "councils beat single models"
  story (hallucination resistance).
- **Math** — GSM8K (`openai/gsm8k`, MIT) `test` split, first ~100; final-answer match
  on the `#### <n>` gold. Clean ablations.
- **Code** — HumanEval (`openai_humaneval`, MIT) ~50 problems; gold = provided unit
  tests, scored pass@1 by executing via the existing `CodeExecutorTool`
  (`backend/tools.py`). MBPP (`google-research-datasets/mbpp`, CC-BY-4.0) as optional
  expansion.

`datasets.py` ships a small generation script (`make_fixtures.py`, run once) that pulls
these via HuggingFace `datasets`, takes the pinned slice, and writes
`backend/eval/data/<suite>.jsonl` committed to the repo for deterministic, offline CI.
Each `EvalItem`: `{id, suite, question, gold, metadata}` (metadata carries license +
source split + row index for provenance). A `--full` flag re-pulls larger official sets
at run time. Record the dataset subset hash in the run manifest (§9).

**Scorers:**
- `exact_match` — normalize case/whitespace/punctuation, compare.
- `math_answer_match` — extract final/boxed number, numeric compare.
- `code_pass` — extract code block, run provided tests in sandbox, pass@1 (0/1).
- `llm_judge` — for open-ended factual: judge model gets (question, gold, prediction) →
  correct/incorrect. Record judge model id + prompt hash for reproducibility.

**Configurations (the field we must beat):**
- `single:<model>` — one completion (the strongest single model is the bar).
- `self_consistency:<model>:k` — k sampled completions + majority vote (Wang et al.).
  A council that can't beat self-consistency isn't worth its cost — this is the honest baseline.
- `senate` — `SenateService` final synthesis.
- `council` — `CouncilService` `direct_answer`.
- **Council ablations:** `council_no_debate`, `council_no_critique`,
  `council_no_election` (heuristic leader), `council_no_tools` — quantify each stage's
  contribution. Driven by config toggles added to `CouncilService`.

**Metrics (`metrics.py`, defined precisely for reproducibility):**
- **accuracy** = correct / total.
- **win-rate vs best single** = mean over items of `1[council_correct ∧ ¬single_correct]`
  minus losses; report net and per-domain.
- **ECE (Expected Calibration Error)** = Σ_bins (n_b/N)·|acc_b − conf_b|. Confidence
  source: Council grade→prob map; single model self-reported confidence or logprob.
  *This is our unique claim: "it answers better AND knows when it's unsure."*
- **cost_usd**, **latency_s** (per item + total), **prompt/completion tokens**.

**Report (`report.py`):** `eval_results/leaderboard.md` + `.json`, with: leaderboard
sorted by accuracy then cost; ablation table; calibration (ECE) table; per-domain
breakdown; a one-line cost/accuracy Pareto note. The `.json` also powers the Phase 4
in-app leaderboard.

**CLI:**
```
uv run python -m backend.eval.run \
  --suite factual,math,code \
  --configs single:gpt-5.2,self_consistency:gpt-5.2:5,senate,council \
  --limit 50 --out eval_results/
```
`--limit` and a `FakeAdapter` dry-run keep CI cheap and deterministic.

### 5B. Flagship feature: Multi-Round Debate / Revision

Insert a debate loop between critique (`_stage2`) and election (`_stage3`) in
`backend/council.py`:

```
opinions  = stage1()
critiques = stage2(opinions)
for r in range(council_debate_max_rounds):          # default 2
    revised = parallel( revise(m, m.opinion, critiques_of_m, others_anon)
                        for m in successful_models )
    if converged(opinions, revised): break          # all changed=False OR answers stable
    opinions  = revised
    critiques = stage2(opinions)                     # re-critique (config-gated)
election(opinions, critiques)                         # runs on FINAL opinions
```

- **Revision prompt:** model sees its own opinion + critiques of it + anonymized peer
  opinions; returns the same structured `COUNCIL_OUTPUT` JSON plus a self-reported
  `changed` flag.
- **Convergence (v1, simple):** stop when every model reports `changed=false`, or when
  answer text is stable (normalized equality / Jaccard ≥ threshold). Caps cost and feeds
  Phase 3 early-exit.
- **Schema (`backend/schemas.py`):** `AgentOpinion` gains `revision_round: int = 0` and
  `changed: bool | None`; `CouncilRun` gains `debate_rounds: list[list[AgentOpinion]]`
  (full transparency) while downstream stages use the final round.
- **Streaming (`backend/streaming.py`):** add `debate_round_started`, `opinion_revised`,
  `debate_converged` events; render live in `frontend/src/{App.tsx,useCouncilStream.ts}`.
- **Config (`backend/config.py`):** `council_debate_enabled=true`,
  `council_debate_max_rounds=2`, `council_debate_recritique=true`,
  `council_debate_convergence="self_report"|"answer_stable"`.

**Acceptance (Phase 1):**
1. `uv run python -m backend.eval.run --suite math --configs single:<m>,council`
   yields a leaderboard with **council accuracy ≥ best single model**.
2. Ablation run shows the **debate delta** (council vs `council_no_debate`).
3. ECE computed and reported; `calibration.json` written.
4. New tests pass: `tests/test_eval_scorers.py` (deterministic scoring),
   `tests/test_debate.py` (debate loop + convergence via `FakeAdapter`),
   `tests/test_metrics.py` (ECE/accuracy/win-rate math).

---

## 6. Phase 2 — Answer-Quality Depth (each validated on the harness)

**6.1 Adversarial tool-grounded verification.** New role **Red-Team Verifier**
(`backend/roles.py`, tools: web_search/code_executor/calculator). New
`backend/verification.py` (`build_verification_prompt` / `parse_verification`). After
debate, the verifier takes top-N `verifiable=true` key claims and tries to *refute* each
via tool calls → `VerificationReport` (per claim: `supported|refuted|unverifiable` +
evidence/source). Results feed `provenance` and nudge the `confidence_grade`. Turns our
already-built-but-off tools into a real grounding step (closes G4).

**6.2 Disagreement as a first-class output (Perplexity's idea).** Compute
`convergence_score` in `council.py` from Stage-1 + final debate opinions; build an
`agreement_map` (which models agree/dissent per key claim). Add both to `CouncilRun`.
Drives Phase 3 early-exit and the Phase 4 "agreement view."

**6.3 Claim-level citations.** Strengthen the synthesis prompt so every consensus/dissent
point cites its source agent labels and tool/web evidence; parse into the existing
`ProvenanceEntry`. With web search on, attach URLs. (Renders in Phase 4.)

**6.4 Measured calibration.** Fit a grade→probability map (Platt/isotonic) from harness
outcomes → `backend/eval/calibration.json`; new `backend/calibration.py` applies it at
runtime so the UI can show "≈X% likely correct" backed by *measured* calibration, not vibes.

**Acceptance:** harness re-run shows verification raises factual accuracy and/or lowers
ECE; citations present and parseable; calibration map reduces ECE vs raw grades.

---

## 7. Phase 3 — Cost & Speed (tradeoffs the harness quantifies)

**7.1 Prompt caching (closes G7; parity with sherifkozman).** In `backend/providers.py`:
Anthropic `cache_control:{type:ephemeral}` on the static system+context block;
OpenAI/OpenRouter automatic caching (structure prompts so the reused prefix — original
query + first opinions — is stable and front-loaded across critique/debate/synthesis to
maximize hits); Gemini cached-content for repeated context. Track `cache_read` tokens in
`UsageMetadata`; surface savings. Config: `provider_prompt_cache_enabled`.

**7.2 Reasoning-budget control (G8).** `ModelRoute` gains `reasoning_effort` /
`thinking_budget`; `providers.py` passes provider-specific params (OpenAI
`reasoning.effort`, Anthropic thinking `budget_tokens`, Gemini thinking level). Per-stage
override: low for opinions, high for synthesis/verification.

**7.3 Smart routing / model tiering.** Extend `backend/orchestrator.py` with a difficulty
estimate; map (query_type, difficulty) → model tier (cheap vs frontier) using an
eval-derived strength table `backend/eval/model_strengths.json` produced by the harness.

**7.4 Early-exit on consensus.** If Stage-1 `convergence_score` ≥ threshold and average
confidence is high, skip debate/critique and go straight to lightweight synthesis. The
harness measures the quality cost so it is a *known* tradeoff, not a silent regression.
Config: `council_early_exit_enabled`, threshold.

**7.5 Per-run cost budget.** `council_max_cost_usd`; `CouncilService` tracks running cost
and degrades gracefully (drop a model / skip debate) when tight; record budget decisions.

**Acceptance:** harness shows caching + early-exit cut cost/latency materially with
accuracy within an agreed tolerance (e.g. ≤1pt); routing improves the cost/accuracy Pareto.

---

## 8. Phase 4 — Product & Trust (surface the deliberation and the proof)

**8.1 Provenance / citation visualization (closes G9).** New `ProvenanceView` in the
frontend rendering the `ProvenanceEntry` tree we already build: claim → source models,
validated_by, challenged_by, tool_verified, citations. "Why believe this answer."

**8.2 In-app leaderboard page.** `GET /api/eval/leaderboard` serves
`eval_results/leaderboard.json`; a Leaderboard view surfaces our public proof inside the app.

**8.3 Health / doctor preflight (parity with sherifkozman).** `uv run python -m
backend.doctor` (and/or `GET /api/health/deep`): tiny generation per configured provider,
report ready/failed; `CouncilService` skips dead providers (extends existing graceful
degradation).

**8.4 Exports.** `GET /api/council/run/{id}/export?format=md|pdf` → shareable
deliberation report; frontend download button (md first, pdf optional).

**8.5 Public API + observability.** Ensure clean OpenAPI (FastAPI auto) + a thin Python
client snippet in docs; add per-stage timing/cost/token trace to schemas/streaming and a
trace panel in the UI.

**Acceptance:** provenance + citations render for a real run; leaderboard page loads from
harness output; `doctor` correctly flags a missing key; export downloads a faithful report.

---

## 9. Cross-Cutting: Reproducibility & Determinism

- Eval runs pin `temperature=0` where supported; self-consistency uses fixed seeds/k.
- Record run manifest: model ids, route hashes, config, dataset subset hash, judge id.
- CI smoke eval uses `FakeAdapter` (no network) so the harness is testable for free.
- Note benchmark-contamination risk; keep a small **private held-out** set and report
  both public and held-out numbers.

---

## 10. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Eval API cost | Curated subsets, `--limit`, prompt caching, cheap judge, FakeAdapter CI |
| Benchmark contamination | Private held-out set; report public + held-out |
| Debate cost blowup | Cap rounds (2), early-exit, caching, re-critique gating |
| LLM-judge bias | Prefer exact/code/math auto-scoring; strong judge + self-consistency on judge |
| Provider API drift | `doctor` preflight + existing retry/backoff |
| Non-determinism in proof | temp=0, seeds, recorded manifests/hashes |
| Code-exec safety | Keep subprocess timeout; sandbox only enabled for eval/verifier paths |

---

## 11. Sequencing & Milestones

- **M0** Phase 0 fixes (small).
- **M1 (keystone)** Phase 1, sub-milestones: **M1a** datasets+scorers+metrics → **M1b**
  baselines+council runner → **M1c** report/leaderboard → **M1d** debate loop+ablations.
  Exit criterion: leaderboard shows council ≥ best single + measured debate delta.
- **M2** Phase 2 — verification, disagreement map, citations, calibration.
- **M3** Phase 3 — caching, reasoning budgets, routing, early-exit, budgets.
- **M4** Phase 4 — provenance viz, leaderboard page, doctor, exports, API/observability.

Each milestone after M1 is **gated by a harness re-run** demonstrating the intended
accuracy/calibration gain at an acceptable cost.

---

## 12. Critical Files Index

**New:** `backend/eval/{__init__,datasets,scorers,baselines,harness,report,metrics,run}.py`,
`backend/eval/data/*.jsonl`, `backend/eval/calibration.json`,
`backend/eval/model_strengths.json`, `backend/verification.py`, `backend/calibration.py`,
`backend/doctor.py`, `eval_results/leaderboard.{md,json}`,
`tests/test_eval_scorers.py`, `tests/test_metrics.py`, `tests/test_debate.py`,
`tests/test_verification.py`.

**Modify:** `backend/council.py` (debate loop, ablation hooks, verification wire-in,
convergence/early-exit), `backend/schemas.py` (debate/verification/convergence/route
fields), `backend/streaming.py` (new events), `backend/config.py` (debate/cache/budget/
reasoning flags), `backend/providers.py` (cost for Anthropic/Google, caching, reasoning
budgets), `backend/election.py` + `CLAUDE.md` (weight reconciliation, doc fixes),
`backend/orchestrator.py` (routing/tiering), `backend/roles.py` (verifier role),
`backend/main.py` (eval/leaderboard/export/health endpoints),
`frontend/src/{App.tsx,types.ts,api.ts,useCouncilStream.ts}` (debate, provenance,
leaderboard, exports).

---

## 13. End-to-End Verification

1. `uv run pytest` — all green, including new scorer/metrics/debate/verification tests.
2. `uv run python -m backend.eval.run --suite factual,math,code --configs single:<m>,self_consistency:<m>:5,senate,council`
   → `eval_results/leaderboard.md` shows **council ≥ best single model** with
   cost/latency/ECE columns and an ablation table.
3. `uv run python -m backend.doctor` flags a missing/invalid provider key.
4. Run the app (`.\start.ps1`): a Council run shows live **debate rounds**, a
   **provenance/citation view**, and a **leaderboard** page; export downloads a report.
5. Every Phase 2–4 feature accepted only when a harness re-run shows the intended
   accuracy/calibration gain at an acceptable cost delta.
