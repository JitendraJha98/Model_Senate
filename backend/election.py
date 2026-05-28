from __future__ import annotations

from statistics import mean

from backend.schemas import AgentOpinion, CouncilCritique, ElectionCandidate, LeaderElection


def compute_election_score(model_id: str, opinions: list[AgentOpinion], critiques: list[CouncilCritique]) -> ElectionCandidate:
    opinion = next(item for item in opinions if item.model_id == model_id)
    completed_critiques = [
        critique for critique in critiques if critique.target_model_id == model_id and critique.status == "completed" and critique.scores
    ]
    rank_score = mean([critique.scores.average for critique in completed_critiques]) if completed_critiques else 0.5
    calibration_score = 1 - abs((opinion.confidence or 0.5) - rank_score)
    claims = opinion.key_claims
    if claims:
        verified = sum(1 for claim in claims if claim.verification_status in {"verified", "partially_verified"})
        tool_score = verified / len(claims)
    else:
        tool_score = 0.5
    first_place_votes = sum(
        1
        for critique in completed_critiques
        if critique.scores and critique.scores.average >= 0.85
    )
    score = (rank_score * 0.6) + (calibration_score * 0.25) + (tool_score * 0.15)
    return ElectionCandidate(
        model_id=model_id,
        display_name=opinion.display_name,
        score=round(score, 4),
        rank_score=round(rank_score, 4),
        calibration_score=round(calibration_score, 4),
        tool_verification_score=round(tool_score, 4),
        first_place_votes=first_place_votes,
    )


def elect_leader(opinions: list[AgentOpinion], critiques: list[CouncilCritique]) -> LeaderElection:
    eligible = [opinion for opinion in opinions if opinion.status in {"completed", "parse_failed"} and opinion.answer.strip()]
    if not eligible:
        raise ValueError("No eligible opinions for leader election")
    candidates = [compute_election_score(opinion.model_id, eligible, critiques) for opinion in eligible]
    candidates.sort(key=lambda item: (-item.score, -item.rank_score, -item.first_place_votes, item.model_id))
    leader = candidates[0]
    validator = candidates[1] if len(candidates) > 1 else None
    return LeaderElection(
        leader_model_id=leader.model_id,
        leader_display_name=leader.display_name,
        validator_model_id=validator.model_id if validator else leader.model_id,
        validator_display_name=validator.display_name if validator else leader.display_name,
        candidates=candidates,
        rationale=f"{leader.display_name} had the highest weighted score across critique quality, calibration, and verification.",
    )
