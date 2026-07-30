from ace.visual_intelligence.contracts import ShotIntent, VisualCandidate
from ace.visual_intelligence.scoring import score_candidate


def test_financial_chart_is_rejected_for_unencrypted_network():
    intent = ShotIntent(
        shot_id="shot-004",
        narration="If the network lacks encryption, other people may see exposed traffic.",
        purpose="explain_mechanism",
        subject="unencrypted_network_traffic",
        preferred_formats=["animated_explainer", "browser_demo", "stock_video"],
        required_elements=["shared_access_point", "multiple_devices", "data_packets", "missing_encryption_lock"],
        forbidden_elements=["financial_chart", "fire", "generic_hacker"],
        literalness="abstract_mechanism",
    )
    candidate = VisualCandidate(
        candidate_id="stock-chart",
        shot_id=intent.shot_id,
        format="stock_video",
        provider="pexels",
        title="Man reading financial chart",
        description="Business analyst studies a financial chart on a computer.",
        origin="licensed_stock",
        license_status="pexels",
        tags=["financial_chart", "business", "computer"],
        width=1080,
        height=1920,
    )
    score = score_candidate(intent, candidate)
    assert score.decision == "rejected"
    assert "financial_chart" in score.forbidden_violations
    assert score.semantic_relevance < 50


def test_original_explainer_scores_high_for_mechanism():
    intent = ShotIntent(
        shot_id="shot-004",
        narration="If the network lacks encryption, traffic may be exposed.",
        purpose="explain_mechanism",
        subject="unencrypted_network_traffic",
        preferred_formats=["animated_explainer", "browser_demo"],
        required_elements=["shared_access_point", "multiple_devices", "data_packets", "missing_encryption_lock"],
        forbidden_elements=["financial_chart", "fire"],
        literalness="abstract_mechanism",
    )
    candidate = VisualCandidate(
        candidate_id="ace-network",
        shot_id=intent.shot_id,
        format="animated_explainer",
        provider="ace_explainer",
        title="Unencrypted network packet flow",
        description="Exposed packets move between multiple devices and a shared access point without a closed lock.",
        origin="ace_generated",
        license_status="account_owned",
        semantic_elements=["shared_access_point", "multiple_devices", "data_packets", "missing_encryption_lock"],
        width=720,
        height=1280,
    )
    score = score_candidate(intent, candidate)
    assert score.decision == "accepted"
    assert score.semantic_relevance >= 90
    assert score.truthfulness == 100


def test_compound_forbidden_term_does_not_match_one_generic_word():
    intent = ShotIntent(
        shot_id="shot-compound",
        narration="Show devices on a shared network.",
        subject="public_wifi_shared_network",
        preferred_formats=["animated_explainer"],
        required_elements=["wireless_router", "multiple_devices", "shared_network"],
        forbidden_elements=["abstract_ai_network", "generic_wifi_router", "financial_chart"],
    )
    candidate = VisualCandidate(
        candidate_id="candidate-network",
        shot_id=intent.shot_id,
        format="animated_explainer",
        provider="ace_explainer",
        title="Shared network topology",
        description="A literal router and several connected devices.",
        tags=["router", "wifi", "devices", "shared_network"],
        semantic_elements=["wireless_router", "multiple_devices", "shared_network"],
        origin="ace_generated",
        license_status="account_owned",
        width=720,
        height=1280,
    )
    score = score_candidate(intent, candidate, thresholds={"minimum_relevance": 0, "minimum_clarity": 0, "minimum_vertical_fit": 0, "minimum_truthfulness": 0})
    assert score.forbidden_violations == []
