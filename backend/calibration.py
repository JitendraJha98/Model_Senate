"""Runtime calibration: map a Council confidence grade to a measured probability.

The harness fits `backend/eval/calibration.json` (grade → empirical accuracy). At runtime
we load it so the UI can say "≈X% likely correct" backed by measured outcomes, not vibes.
Falls back to sensible defaults when no fitted map exists yet.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_GRADE_PROB = {"A": 0.9, "B": 0.75, "C": 0.5, "D": 0.3, "F": 0.1}
_CALIBRATION_PATH = Path(__file__).parent / "eval" / "calibration.json"


def load_calibration_map() -> dict[str, float]:
    """Load the fitted grade→probability map, or the defaults if none/invalid."""
    if _CALIBRATION_PATH.exists():
        try:
            data = json.loads(_CALIBRATION_PATH.read_text(encoding="utf-8"))
            fitted = {str(k): float(v) for k, v in data.items()}
            if fitted:
                # Backfill grades the fit didn't observe so every grade resolves.
                return {**DEFAULT_GRADE_PROB, **fitted}
        except (ValueError, TypeError, OSError):
            pass
    return dict(DEFAULT_GRADE_PROB)


def calibrated_probability(grade: str | None, calibration: dict[str, float] | None = None) -> float | None:
    """Probability-correct for a grade using the (optionally provided) calibration map."""
    if not grade:
        return None
    cal = calibration if calibration is not None else load_calibration_map()
    return cal.get(grade, DEFAULT_GRADE_PROB.get(grade))
