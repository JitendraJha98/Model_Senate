"""End-to-end harness smoke test, fully offline via a knowledge-bearing fake adapter."""

from pathlib import Path

from backend.eval.baselines import EvalContext
from backend.eval.harness import run_eval
from backend.eval.report import render_markdown, write_report
from backend.schemas import ModelRoute, UsageMetadata
from backend.storage import ConversationStore

# Answers for the bundled factual fixture, matched by substring of the question/prompt.
ANSWERS = {
    "chemical symbol for gold": "Au",
    "first humans land on the moon": "1969",
    "capital city of japan": "Tokyo",
    "how many continents": "7",
    "largest planet": "Jupiter",
}

ORCHESTRATOR_PLAN = (
    '{"query_type":"factual","is_multi_part":false,"sub_questions":[],'
    '"role_assignments":{"m1":"Fact Verifier","m2":"Independent Expert"},'
    '"tool_assignments":{"m1":[],"m2":[]},"decomposition_rationale":"single"}'
)
CRITIQUE = (
    '{"reviews":{"Agent B":{"factual_accuracy_score":0.9,"logical_validity_score":0.9,'
    '"completeness_score":0.9,"calibration_score":0.9,"overall_rank":1,'
    '"strengths":["accurate"],"weaknesses":[],"corrective_additions":[]}}}'
)
VALIDATION = (
    '{"verdict":"approved","checks":{"dissents_addressed":true,"confidence_calibrated":true,'
    '"no_hallucinations":true,"answers_original_query":true,"next_checks_actionable":true},'
    '"issues":[],"addendum":null}'
)


def _lookup(text: str) -> str:
    low = text.lower()
    for key, val in ANSWERS.items():
        if key in low:
            return val
    return "unknown"


class KnowledgeAdapter:
    """Answers the factual fixture correctly at every stage of both pipelines."""

    async def complete(self, route, messages, *, json_mode: bool = False):
        system = messages[0].content if messages else ""
        user = " ".join(m.content for m in messages if m.role == "user")
        ans = _lookup(user)
        usage = UsageMetadata(prompt_tokens=5, completion_tokens=5, total_tokens=10, cost=0.001)
        if "orchestration agent" in system:
            return ORCHESTRATOR_PLAN, usage, 5
        if "critique agent" in system:
            return CRITIQUE, usage, 5
        if "elected Synthesizer" in system:
            return (
                f'{{"direct_answer":"{ans}","consensus_points":["agree"],"dissent_points":[],'
                '"unresolved_conflicts":[],"confidence_grade":"A","recommended_next_checks":[],'
                '"provenance_map":{}}',
                usage,
                5,
            )
        if "validate Model Council" in system:
            return VALIDATION, usage, 5
        if "Answer the question directly" in system:  # single / self_consistency
            return ans, usage, 5
        # Stage-1 first opinion (council).
        return (
            f'Reasoning.\n\nCOUNCIL_OUTPUT:\n{{"answer_summary":"{ans}","confidence":0.9,'
            '"key_claims":[],"uncertainties":[]}',
            usage,
            5,
        )


def _ctx(tmp_path: Path) -> EvalContext:
    routes = [
        ModelRoute(id="m1", provider="openrouter", model="one", display_name="One"),
        ModelRoute(id="m2", provider="openrouter", model="two", display_name="Two"),
    ]
    return EvalContext(
        routes=routes,
        adapters={"openrouter": KnowledgeAdapter()},
        store=ConversationStore(tmp_path),
        tool_registry={},
        orchestrator_model_id="m1",
        council_ids=["m1", "m2"],
        debate_enabled=False,
    )


async def test_harness_runs_council_and_single_offline(tmp_path: Path):
    report = await run_eval(
        suites=["factual"],
        configs=["single:m1", "council"],
        ctx=_ctx(tmp_path),
    )
    overall = {r.config: r for r in report.per_config_overall}
    assert overall["single:m1"].accuracy == 1.0
    assert overall["council"].accuracy == 1.0
    # Acceptance: council accuracy >= best single model.
    assert overall["council"].accuracy >= overall["single:m1"].accuracy
    assert report.best_single_config == "single:m1"
    # Council reported grade A on every (correct) item → calibration fitted for grade A.
    assert report.calibration.get("A") == 1.0
    # Cost is tracked (non-zero) now that adapters report cost.
    assert overall["council"].total_cost_usd > 0


async def test_harness_ablation_and_report_render(tmp_path: Path):
    report = await run_eval(
        suites=["factual"],
        configs=["single:m1", "council", "council_no_debate"],
        ctx=_ctx(tmp_path),
    )
    md = render_markdown(report)
    assert "Council Evaluation Leaderboard" in md
    assert "council_no_debate" in md
    path = write_report(report, tmp_path / "eval_out")
    assert path.exists()
    assert (path.parent / "leaderboard.json").exists()
