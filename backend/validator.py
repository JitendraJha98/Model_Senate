from __future__ import annotations

import json
import re

from backend.schemas import CouncilCritique, CouncilSynthesis, SynthesisValidation


_VALIDATION_CHECKS = [
    "dissents_addressed",
    "confidence_calibrated",
    "no_hallucinations",
    "answers_original_query",
    "next_checks_actionable",
]


def build_validation_prompt(
    synthesis: CouncilSynthesis,
    critiques: list[CouncilCritique],
    original_query: str,
) -> str:
    critique_flags = "\n".join(
        f"- {c.reviewer_display_name} on {c.target_display_name}: {', '.join(c.corrective_additions)}"
        for c in critiques
        if c.corrective_additions
    )

    return f"""\
You are validating a Model Council synthesis against the original query.

Answer these five checks (true = passed, false = failed):
1. dissents_addressed: Are all major dissent points from critiques addressed in the synthesis?
2. confidence_calibrated: Does the confidence grade match the evidence \
(not over- or under-confident)?
3. no_hallucinations: Are any specific facts or citations present that were NOT in the \
original council opinions? (false = hallucination detected)
4. answers_original_query: Does the direct_answer actually answer the original query?
5. next_checks_actionable: Are the recommended_next_checks specific and actionable?

Return ONLY valid JSON:
{{
  "verdict": "approved",
  "checks": {{
    "dissents_addressed": true,
    "confidence_calibrated": true,
    "no_hallucinations": true,
    "answers_original_query": true,
    "next_checks_actionable": true
  }},
  "issues": ["issue if any"],
  "addendum": "short addendum if verdict is flagged, else null"
}}

verdict must be "approved" if all checks pass, "flagged" if any check fails.

Original query:
{original_query}

Synthesis:
{synthesis.raw_content or synthesis.direct_answer}

Critique flags from Stage 2:
{critique_flags or "None"}
"""


def parse_validation_result(
    content: str,
    validator_model_id: str | None,
    validator_display_name: str | None,
    latency_ms: int | None,
) -> SynthesisValidation:
    try:
        data = json.loads(_extract_json(content))
        verdict = data.get("verdict", "flagged")
        if verdict not in {"approved", "flagged"}:
            verdict = "flagged"

        raw_checks = data.get("checks") or {}
        checks: dict[str, bool] = {k: bool(raw_checks.get(k, False)) for k in _VALIDATION_CHECKS}

        # Derive verdict from checks if it conflicts
        all_passed = all(checks.values())
        if all_passed and verdict == "flagged":
            verdict = "approved"
        elif not all_passed and verdict == "approved":
            verdict = "flagged"

        return SynthesisValidation(
            validator_model_id=validator_model_id,
            validator_display_name=validator_display_name,
            status="completed",
            verdict=verdict,
            checks=checks,
            issues=list(data.get("issues") or []),
            addendum=data.get("addendum"),
            latency_ms=latency_ms,
        )
    except Exception:
        return SynthesisValidation(
            validator_model_id=validator_model_id,
            validator_display_name=validator_display_name,
            status="completed",
            verdict="flagged",
            checks={k: False for k in _VALIDATION_CHECKS},
            issues=["Validator returned unstructured output."],
            addendum=content[:500] if content else None,
            latency_ms=latency_ms,
        )


def _extract_json(content: str) -> str:
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found")
    return match.group(0)
