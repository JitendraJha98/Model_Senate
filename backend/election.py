from __future__ import annotations

from statistics import mean

from backend.schemas import AgentOpinion, CouncilCritique, LeaderElection


# Base dimension weights. When no candidate produced verifiable claims the tool
# dimension is meaningless, so its weight is redistributed across the other two
# (see `_dimension_weights`) rather than silently dragging every score down.
_BASE_WEIGHTS = {"rank": 0.40, "calibration": 0.30, "tool": 0.30}


def _dimension_weights(opinions: list[AgentOpinion]) -> dict[str, float]:
    tool_active = any(cl.verifiable for o in opinions for cl in o.key_claims)
    if tool_active:
        return dict(_BASE_WEIGHTS)
    active = _BASE_WEIGHTS["rank"] + _BASE_WEIGHTS["calibration"]
    return {
        "rank": _BASE_WEIGHTS["rank"] / active,
        "calibration": _BASE_WEIGHTS["calibration"] / active,
        "tool": 0.0,
    }


def compute_election_score(
    model_id: str,
    opinions: list[AgentOpinion],
    critiques: list[CouncilCritique],
    weights: dict[str, float],
) -> tuple[float, dict[str, float]]:
    """Return (final_score, breakdown_dict) for one candidate."""
    # Each reviewer ranks the OTHER candidates, so ranks span 1..(n_models-1).
    n_targets = max(1, len(opinions) - 1)

    # --- Rank score ---
    relevant = [c for c in critiques if c.target_model_id == model_id and c.overall_rank is not None]
    if relevant:
        avg_rank = mean(c.overall_rank for c in relevant)  # type: ignore[arg-type]
        rank_score = max(0.0, min(1.0, (n_targets - avg_rank + 1) / n_targets))
    else:
        # No ranking signal (e.g. single-model council): neutral, not disqualifying.
        rank_score = 0.5

    # --- Calibration score ---
    opinion = next((o for o in opinions if o.model_id == model_id), None)
    stated_confidence = opinion.confidence if (opinion and opinion.confidence is not None) else 0.5
    accuracy_scores = [
        c.factual_accuracy_score
        for c in critiques
        if c.target_model_id == model_id and c.factual_accuracy_score is not None
    ]
    avg_accuracy = mean(accuracy_scores) if accuracy_scores else 0.5
    calibration_score = max(0.0, 1.0 - abs(stated_confidence - avg_accuracy))

    # --- Tool verification ratio ---
    verifiable = [cl for cl in (opinion.key_claims if opinion else []) if cl.verifiable]
    verified = [cl for cl in verifiable if cl.verified]
    tool_ratio = len(verified) / len(verifiable) if verifiable else 0.0

    final_score = (
        weights["rank"] * rank_score
        + weights["calibration"] * calibration_score
        + weights["tool"] * tool_ratio
    )

    breakdown = {
        "rank_score": round(rank_score, 3),
        "calibration_score": round(calibration_score, 3),
        "tool_verification_ratio": round(tool_ratio, 3),
        "tool_dimension_active": 1.0 if weights["tool"] > 0 else 0.0,
        "final_score": round(final_score, 3),
    }
    return final_score, breakdown


def elect_leader(opinions: list[AgentOpinion], critiques: list[CouncilCritique]) -> LeaderElection:
    eligible = [o for o in opinions if o.status in {"completed", "parse_failed"} and o.content.strip()]
    if not eligible:
        raise ValueError("No eligible opinions for leader election")

    weights = _dimension_weights(eligible)
    scores: dict[str, float] = {}
    breakdowns: dict[str, dict[str, float]] = {}
    for opinion in eligible:
        score, breakdown = compute_election_score(opinion.model_id, eligible, critiques, weights)
        scores[opinion.model_id] = score
        breakdowns[opinion.model_id] = breakdown

    # Sort descending; the leader must produce structured synthesis, so a model that
    # returned a clean structured opinion outranks one that only parsed as prose.
    # Tiebreak: score → accuracy → first_place_votes → alphabetical model_id
    def sort_key(o: AgentOpinion) -> tuple:
        mid = o.model_id
        parsed_tier = 0 if (o.status == "completed" and o.structured_output_parsed) else 1
        accuracy = mean(
            c.factual_accuracy_score
            for c in critiques
            if c.target_model_id == mid and c.factual_accuracy_score is not None
        ) if any(c.target_model_id == mid and c.factual_accuracy_score is not None for c in critiques) else 0.0
        first_place = sum(1 for c in critiques if c.target_model_id == mid and c.overall_rank == 1)
        return (parsed_tier, -scores[mid], -accuracy, -first_place, mid)

    sorted_models = sorted(eligible, key=sort_key)
    winner = sorted_models[0]
    runner_up = sorted_models[1] if len(sorted_models) > 1 else winner

    was_tie = abs(scores[winner.model_id] - scores[runner_up.model_id]) < 0.02

    return LeaderElection(
        elected_model_id=winner.model_id,
        elected_display_name=winner.display_name,
        election_score=round(scores[winner.model_id], 4),
        runner_up_model_id=runner_up.model_id,
        runner_up_display_name=runner_up.display_name,
        runner_up_score=round(scores[runner_up.model_id], 4),
        all_scores={mid: round(s, 4) for mid, s in scores.items()},
        score_breakdown=breakdowns,
        rationale=build_election_rationale(winner, breakdowns[winner.model_id]),
        was_tie_broken=was_tie,
    )


def build_election_rationale(winner: AgentOpinion, breakdown: dict[str, float]) -> str:
    parts = []
    if breakdown["rank_score"] >= 0.7:
        parts.append("highest peer ranking")
    if breakdown["tool_verification_ratio"] >= 0.5:
        parts.append(f"{int(breakdown['tool_verification_ratio'] * 100)}% tool-verified claims")
    if breakdown["calibration_score"] >= 0.7:
        parts.append("well-calibrated confidence")
    if not parts:
        parts.append("best overall weighted score")
    return f"{winner.display_name} elected: {', '.join(parts)}."
