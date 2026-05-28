from __future__ import annotations

from backend.schemas import CouncilRun, ReintegrationOutput


def detect_contradictions(sub_runs: list[CouncilRun]) -> list[str]:
    flagged: list[str] = []
    for run in sub_runs:
        if run.validation and run.validation.status in {"flagged", "approved_with_caveats"}:
            flagged.extend(run.validation.issues)
    return flagged


def parse_reintegration_result(content: str) -> ReintegrationOutput:
    return ReintegrationOutput(status="completed", final_answer=content, raw_content=content)
