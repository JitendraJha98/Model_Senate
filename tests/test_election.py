from backend.election import elect_leader
from backend.schemas import AgentOpinion, CouncilCritique, CritiqueScore


def test_election_prefers_best_scored_candidate():
    opinions = [
        AgentOpinion(model_id="m1", display_name="One", provider="openrouter", role="Independent Expert", status="completed", answer="A", confidence=0.8),
        AgentOpinion(model_id="m2", display_name="Two", provider="openrouter", role="Independent Expert", status="completed", answer="B", confidence=0.7),
    ]
    critiques = [
        CouncilCritique(
            reviewer_model_id="m2",
            reviewer_display_name="Two",
            target_model_id="m1",
            target_display_name="One",
            critique_role="Accuracy Auditor",
            status="completed",
            scores=CritiqueScore(accuracy=0.9, logic=0.9, completeness=0.9, calibration=0.9),
        ),
        CouncilCritique(
            reviewer_model_id="m1",
            reviewer_display_name="One",
            target_model_id="m2",
            target_display_name="Two",
            critique_role="Accuracy Auditor",
            status="completed",
            scores=CritiqueScore(accuracy=0.4, logic=0.4, completeness=0.4, calibration=0.4),
        ),
    ]

    election = elect_leader(opinions, critiques)

    assert election.leader_model_id == "m1"
    assert election.validator_model_id == "m2"
