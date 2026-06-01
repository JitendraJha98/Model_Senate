from __future__ import annotations

import json
import re

from backend.schemas import CouncilRun, ReintegrationOutput


def detect_contradictions(sub_runs: list[CouncilRun]) -> list[str]:
    """Find contradictions across sub-runs by looking at conflicting grades and flagged validations."""
    contradictions: list[str] = []

    # Flag cross-sub-answer conflicts: high-confidence run vs low-confidence run on related topics
    grades = {run.id: run.confidence_grade for run in sub_runs if run.confidence_grade}
    high = {rid for rid, g in grades.items() if g in ("A", "B")}
    low = {rid for rid, g in grades.items() if g in ("D", "F")}
    if high and low:
        contradictions.append(
            f"Confidence grade conflict: {len(high)} sub-answers rated A/B vs {len(low)} rated D/F — "
            "verify that high-confidence conclusions are consistent with low-confidence ones."
        )

    # Flag validation issues from sub-runs
    for run in sub_runs:
        if run.validation and run.validation.verdict == "flagged":
            for issue in run.validation.issues:
                contradictions.append(f"Sub-question '{run.prompt[:60]}': {issue}")

    return contradictions


def build_reintegration_prompt(
    sub_runs: list[CouncilRun],
    original_query: str,
    contradictions: list[str],
) -> str:
    sub_answers = "\n\n".join(
        f"### Sub-question {i + 1}: {run.prompt}\n"
        f"Answer: {run.synthesis.direct_answer if run.synthesis else 'No synthesis produced.'}\n"
        f"Confidence grade: {run.confidence_grade or 'N/A'}"
        for i, run in enumerate(sub_runs)
    )
    contradiction_block = "\n".join(f"- {c}" for c in contradictions) or "None detected."

    return f"""\
You are the Re-integration Agent in Model Council.

The original composite query was decomposed into sub-questions. Each sub-question was answered \
independently. Your job is to assemble a unified, coherent final answer that:
1. Maintains internal consistency across all sub-answers.
2. Notes where sub-questions had conflicting conclusions.
3. Inherits the lowest confidence grade of any sub-run.

Return ONLY valid JSON:
{{
  "unified_answer": "complete unified answer",
  "contradictions_resolved": ["contradiction resolved and how"],
  "contradictions_unresolved": ["contradiction that remains open"],
  "final_confidence_grade": "A|B|C|D|F"
}}

Original composite query:
{original_query}

Sub-question answers:
{sub_answers}

Cross-sub-answer contradictions detected:
{contradiction_block}
"""


def parse_reintegration_result(
    content: str,
    model_id: str,
    display_name: str,
    sub_run_ids: list[str],
    latency_ms: int | None,
) -> ReintegrationOutput:
    try:
        data = json.loads(_extract_json(content))
        grade = data.get("final_confidence_grade")
        if grade not in ("A", "B", "C", "D", "F"):
            grade = None
        return ReintegrationOutput(
            model_id=model_id,
            display_name=display_name,
            status="completed",
            unified_answer=str(data.get("unified_answer") or ""),
            sub_run_ids=sub_run_ids,
            contradictions_resolved=list(data.get("contradictions_resolved") or []),
            contradictions_unresolved=list(data.get("contradictions_unresolved") or []),
            final_confidence_grade=grade,
            latency_ms=latency_ms,
        )
    except Exception:
        return ReintegrationOutput(
            model_id=model_id,
            display_name=display_name,
            status="completed",
            unified_answer=content,
            sub_run_ids=sub_run_ids,
            latency_ms=latency_ms,
        )


def _extract_json(content: str) -> str:
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found")
    return match.group(0)
