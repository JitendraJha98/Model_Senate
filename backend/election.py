from __future__ import annotations

from statistics import mean

from backend.schemas import AgentOpinion, CouncilCritique, LeaderElection


def compute_election_score(
    model_id: str,
    opinions: list[AgentOpinion],
    critiques: list[CouncilCritique],
) -> tuple[float, dict[str, float]]:
    """Return (final_score, breakdown_dict) for one candidate."""
    n_models = len(opinions)

    # --- Rank score (40%) ---
    # Normalize rank so rank 1 in N-model council → 1.0, rank N → 1/N
    relevant = [c for c in critiques if c.target_model_id == model_id and c.overall_rank is not None]
    if relevant:
        avg_rank = mean(c.overall_rank for c in relevant)  # type: ignore[arg-type]
        rank_score = (n_models - avg_rank + 1) / n_models
    else:
        rank_score = 0.0

    # --- Calibration score (30%) ---
    opinion = next((o for o in opinions if o.model_id == model_id), None)
    stated_confidence = opinion.confidence if (opinion and opinion.confidence is not None) else 0.5
    accuracy_scores = [
        c.factual_accuracy_score
        for c in critiques
        if c.target_model_id == model_id and c.factual_accuracy_score is not None
    ]
    avg_accuracy = mean(accuracy_scores) if accuracy_scores else 0.5
    calibration_score = max(0.0, 1.0 - abs(stated_confidence - avg_accuracy))

    # --- Tool verification ratio (30%) ---
    verifiable = [cl for cl in (opinion.key_claims if opinion else []) if cl.verifiable]
    verified = [cl for cl in verifiable if cl.verified]
    tool_ratio = len(verified) / len(verifiable) if verifiable else 0.0

    final_score = 0.40 * rank_score + 0.30 * calibration_score + 0.30 * tool_ratio

    breakdown = {
        "rank_score": round(rank_score, 3),
        "calibration_score": round(calibration_score, 3),
        "tool_verification_ratio": round(tool_ratio, 3),
        "final_score": round(final_score, 3),
    }
    return final_score, breakdown


def elect_leader(opinions: list[AgentOpinion], critiques: list[CouncilCritique]) -> LeaderElection:
    eligible = [o for o in opinions if o.status in {"completed", "parse_failed"} and o.content.strip()]
    if not eligible:
        raise ValueError("No eligible opinions for leader election")

    scores: dict[str, float] = {}
    breakdowns: dict[str, dict[str, float]] = {}
    for opinion in eligible:
        score, breakdown = compute_election_score(opinion.model_id, eligible, critiques)
        scores[opinion.model_id] = score
        breakdowns[opinion.model_id] = breakdown

    # Sort descending; tiebreak: accuracy → first_place_votes → alphabetical model_id
    def sort_key(o: AgentOpinion) -> tuple:
        mid = o.model_id
        accuracy = mean(
            c.factual_accuracy_score
            for c in critiques
            if c.target_model_id == mid and c.factual_accuracy_score is not None
        ) if any(c.target_model_id == mid and c.factual_accuracy_score is not None for c in critiques) else 0.0
        first_place = sum(1 for c in critiques if c.target_model_id == mid and c.overall_rank == 1)
        return (-scores[mid], -accuracy, -first_place, mid)

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
