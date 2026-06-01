from backend.election import elect_leader
from backend.schemas import AgentOpinion, CouncilCritique


def _opinion(model_id: str, display: str, confidence: float = 0.8) -> AgentOpinion:
    return AgentOpinion(
        model_id=model_id,
        display_name=display,
        provider="openrouter",
        role="Independent Expert",
        status="completed",
        content="Test answer.",
        confidence=confidence,
    )


def _critique(reviewer_id: str, target_id: str, target_display: str, accuracy: float, rank: int) -> CouncilCritique:
    return CouncilCritique(
        reviewer_model_id=reviewer_id,
        reviewer_display_name=reviewer_id,
        reviewer_critique_role="Challenger",
        target_model_id=target_id,
        target_display_name=target_display,
        status="completed",
        factual_accuracy_score=accuracy,
        logical_validity_score=accuracy,
        completeness_score=accuracy,
        calibration_score=accuracy,
        overall_rank=rank,
    )


def test_election_prefers_best_scored_candidate():
    opinions = [
        _opinion("m1", "One", confidence=0.9),
        _opinion("m2", "Two", confidence=0.5),
    ]
    critiques = [
        _critique("m2", "m1", "One", accuracy=0.9, rank=1),
        _critique("m1", "m2", "Two", accuracy=0.3, rank=1),
    ]

    election = elect_leader(opinions, critiques)

    assert election.elected_model_id == "m1"
    assert election.runner_up_model_id == "m2"
    assert election.election_score > election.runner_up_score


def test_election_returns_all_scores():
    opinions = [_opinion("m1", "One"), _opinion("m2", "Two")]
    critiques = [
        _critique("m2", "m1", "One", accuracy=0.8, rank=1),
        _critique("m1", "m2", "Two", accuracy=0.6, rank=1),
    ]

    election = elect_leader(opinions, critiques)

    assert "m1" in election.all_scores
    assert "m2" in election.all_scores
    assert "m1" in election.score_breakdown
    assert isinstance(election.was_tie_broken, bool)
    assert election.rationale != ""


def test_election_single_model_is_both_winner_and_runner_up():
    opinions = [_opinion("m1", "One")]
    election = elect_leader(opinions, [])

    assert election.elected_model_id == "m1"
    assert election.runner_up_model_id == "m1"
