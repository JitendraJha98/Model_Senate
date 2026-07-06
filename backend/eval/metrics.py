"""Pure metric functions — accuracy, win-rate, and Expected Calibration Error.

Kept dependency-free and side-effect-free so they are trivially unit-testable.
"""

from __future__ import annotations


def accuracy(correct_flags: list[bool]) -> float:
    return sum(1 for c in correct_flags if c) / len(correct_flags) if correct_flags else 0.0


def win_rate(candidate_correct: list[bool], baseline_correct: list[bool]) -> float:
    """Net win-rate of candidate vs baseline over aligned items.

    +1 where candidate is right and baseline wrong, -1 where the reverse, 0 on ties.
    Returns the mean (range -1..1). Requires equal-length aligned lists.
    """
    if len(candidate_correct) != len(baseline_correct):
        raise ValueError("win_rate requires aligned, equal-length result lists")
    if not candidate_correct:
        return 0.0
    net = sum(
        1 if c and not b else -1 if b and not c else 0
        for c, b in zip(candidate_correct, baseline_correct)
    )
    return net / len(candidate_correct)


def expected_calibration_error(
    confidences: list[float], correct_flags: list[bool], n_bins: int = 10
) -> float:
    """ECE = Σ_bins (n_b / N) · |accuracy_b − confidence_b|.

    Only samples with a confidence value participate (align the two lists first).
    """
    paired = [(c, bool(ok)) for c, ok in zip(confidences, correct_flags) if c is not None]
    if not paired:
        return 0.0
    total = len(paired)
    ece = 0.0
    for b in range(n_bins):
        lo = b / n_bins
        hi = (b + 1) / n_bins
        # Last bin is closed on the right so confidence == 1.0 is included.
        bucket = [
            (conf, ok) for conf, ok in paired
            if (lo <= conf < hi) or (b == n_bins - 1 and conf == hi)
        ]
        if not bucket:
            continue
        avg_conf = sum(conf for conf, _ in bucket) / len(bucket)
        acc = sum(1 for _, ok in bucket if ok) / len(bucket)
        ece += (len(bucket) / total) * abs(acc - avg_conf)
    return ece


def fit_calibration(grades: list[str], correct_flags: list[bool]) -> dict[str, float]:
    """Empirical accuracy per confidence grade → the grade→probability map.

    Written to `calibration.json` so runtime confidence reflects measured outcomes.
    """
    buckets: dict[str, list[bool]] = {}
    for grade, ok in zip(grades, correct_flags):
        if grade:
            buckets.setdefault(grade, []).append(bool(ok))
    return {grade: round(accuracy(flags), 4) for grade, flags in buckets.items()}
