from ace.visual_intelligence.contracts import ShotIntent, VisualCandidate, VisualDecision, VisualScore


def test_contract_round_trips():
    intent = ShotIntent(
        shot_id="shot-004",
        narration="If the network lacks encryption, traffic may be exposed.",
        purpose="explain_mechanism",
        subject="unencrypted_network_traffic",
        preferred_formats=["animated_explainer", "stock_video", "animated_explainer"],
        required_elements=["data_packets", "data_packets"],
    )
    assert ShotIntent.from_dict(intent.to_dict()) == intent
    candidate = VisualCandidate(
        candidate_id="candidate-1",
        shot_id=intent.shot_id,
        format="animated_explainer",
        provider="ace_explainer",
        title="Packet flow",
        semantic_elements=["data_packets"],
    )
    assert VisualCandidate.from_dict(candidate.to_dict()) == candidate
    score = VisualScore(
        candidate_id=candidate.candidate_id,
        shot_id=intent.shot_id,
        semantic_relevance=95,
        clarity=90,
        required_element_coverage=100,
        vertical_fit=100,
        style_match=90,
        truthfulness=100,
        visual_quality=85,
        provenance_confidence=100,
        duplicate_risk=0,
        overall=94,
        decision="accepted",
    )
    assert VisualScore.from_dict(score.to_dict()) == score
    decision = VisualDecision(
        shot_id=intent.shot_id,
        selected_candidate_id=candidate.candidate_id,
        status="accepted",
        score=94,
        reason="Best candidate.",
        candidate_count=1,
    )
    assert VisualDecision.from_dict(decision.to_dict()) == decision
