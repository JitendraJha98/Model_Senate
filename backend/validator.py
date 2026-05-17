from __future__ import annotations

import json
import re

from backend.schemas import CouncilCritique, CouncilSynthesis, SynthesisValidation


def build_validation_prompt(synthesis: CouncilSynthesis, critiques: list[CouncilCritique], original_query: str) -> str:
    critique_flags = "\n".join(
        f"- {critique.reviewer_display_name} on {critique.target_display_name}: {', '.join(critique.flags)}"
        for critique in critiques
        if critique.flags
    )
    return f"""Validate this Model Council synthesis against the original query.

Return ONLY JSON:
{{
  "status": "approved|approved_with_caveats|flagged",
  "issues": ["issue"],
  "addendum": "short addendum or null"
}}

Original query:
{original_query}

Synthesis:
{synthesis.raw_content or synthesis.direct_answer}

Critique flags:
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
        status = data.get("status", "approved_with_caveats")
        if status not in {"approved", "approved_with_caveats", "flagged"}:
            status = "approved_with_caveats"
        return SynthesisValidation(
            validator_model_id=validator_model_id,
            validator_display_name=validator_display_name,
            status=status,
            issues=list(data.get("issues") or []),
            addendum=data.get("addendum"),
            raw_content=content,
            latency_ms=latency_ms,
        )
    except Exception:
        return SynthesisValidation(
            validator_model_id=validator_model_id,
            validator_display_name=validator_display_name,
            status="approved_with_caveats",
            issues=["Validator returned unstructured output."],
            addendum=content,
            raw_content=content,
            latency_ms=latency_ms,
        )


def _extract_json(content: str) -> str:
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found")
    return match.group(0)
