# Milestone 1 — Eval Harness + Multi-Round Debate (design)

Keystone of the ROADMAP: turn "fancier pipeline" into *provably better*. Two coupled parts.

## Part A — Multi-round debate (backend)

Insert a debate/revision loop between critique (Stage 2) and election (Stage 3) in
`CouncilService`.

- **Schemas** (`backend/schemas.py`): `AgentOpinion` gains `revision_round: int = 0` and
  `changed: bool | None`; `CouncilRun` gains `debate_rounds: list[list[AgentOpinion]]`
  (full transparency; downstream stages consume the final round).
- **Config** (`backend/config.py`): `council_debate_enabled=True`,
  `council_debate_max_rounds=2`, `council_debate_recritique=True`,
  `council_debate_convergence="self_report"` (`"answer_stable"` alt).
- **Ablation toggles** are per-run constructor kwargs on `CouncilService` (the harness
  flips them without touching global settings): `debate_enabled`, `debate_max_rounds`,
  `debate_recritique`, `enable_critique`, `enable_election`, `enable_tools`. All default
  to preserve today's behavior + the new debate default.
- **Loop:** for each round, every successful model revises its own opinion given (its
  opinion + critiques of it + anonymized peers), returning `COUNCIL_OUTPUT` + a `changed`
  flag. Stop when all `changed=false` (self_report) or answers are stable
  (answer_stable). Re-critique between rounds when `debate_recritique`. Election runs on
  the FINAL opinions.
- **Streaming** (`backend/streaming.py` consumers): emit `debate_round_started`,
  `opinion_revised`, `debate_converged`.

## Part B — Eval harness (`backend/eval/`)

Self-contained package; eval DTOs live in the package, not `backend/schemas.py`.

| File | Responsibility |
|---|---|
| `datasets.py` | `EvalItem`; `load_suite(name) -> list[EvalItem]` from `data/<suite>.jsonl` |
| `scorers.py` | `Score`; `exact_match`, `math_answer_match`, `code_pass`, `llm_judge`; `score_prediction()` dispatch |
| `metrics.py` | pure: `accuracy`, `win_rate`, `expected_calibration_error`, `fit_calibration` |
| `baselines.py` | `Prediction`; `run_config(cfg, item, ctx)` for `single:*`, `self_consistency:*:k`, `senate`, `council`, `council_no_{debate,critique,election,tools}` |
| `harness.py` | `EvalContext`, `EvalReport`; `run_eval(suites, configs, limit, ctx)` |
| `report.py` | `write_report()` → `eval_results/leaderboard.{md,json}` + `calibration.json` |
| `run.py` | argparse CLI (`python -m backend.eval.run`) |
| `data/*.jsonl` | small curated, committed, offline fixtures (factual/math/code) |
| `make_fixtures.py` | optional regeneration from HuggingFace (needs `datasets`+network) |

- **Confidence for ECE:** council grade→prob (`A=.9,B=.75,C=.5,D=.3,F=.1`); single model
  self-reported confidence (fallback 0.5).
- **Offline + deterministic:** fixtures committed; all tests drive `FakeAdapter`-style
  adapters (no network), matching `tests/test_council.py`.

## Tests
`tests/test_eval_scorers.py`, `tests/test_metrics.py`, `tests/test_debate.py`.

## Verify
`uv run python -m pytest` green; `python -m backend.eval.run --suite math
--configs single:m1,council --limit N` writes a leaderboard where council ≥ best single
on the fixture, plus an ablation column for the debate delta.
