from pathlib import Path

from ace.visual_intelligence.contracts import ShotIntent
from ace.visual_intelligence.tournament import run_tournament, validate


def test_tournament_prefers_original_explainer_for_abstract_mechanism(generation: Path, workspace: Path):
    intent = ShotIntent(
        shot_id="shot-001",
        narration="If the network lacks encryption, other people may see exposed traffic.",
        purpose="explain_mechanism",
        subject="unencrypted_network_traffic",
        mood="serious_technical",
        preferred_formats=["animated_explainer", "browser_demo", "stock_video", "minimal_screen"],
        required_elements=["shared_access_point", "multiple_devices", "data_packets", "missing_encryption_lock"],
        forbidden_elements=["fire", "financial_chart", "office_worker", "generic_hacker"],
        literalness="abstract_mechanism",
    )
    selected, score, decision, candidates, _ = run_tournament(
        generation,
        intent,
        duration=2.4,
        workspace=workspace,
        resource_finder=lambda *args, **kwargs: [],
        cloud_judge=False,
        animate_explainers=False,
    )
    assert selected.provider == "ace_explainer"
    assert selected.format == "animated_explainer"
    assert score.semantic_relevance >= 90
    assert decision.status in {"accepted", "fallback"}
    assert len(candidates) >= 2


def test_visual_validation_records_explanations(generation: Path, workspace: Path):
    intent = ShotIntent(
        shot_id="shot-001",
        narration="Encrypted packets travel through a protected connection.",
        purpose="explain_mechanism",
        subject="encrypted_connection",
        preferred_formats=["animated_explainer", "minimal_screen"],
        required_elements=["data_packets", "encryption_lock", "protected_connection"],
        forbidden_elements=["financial_chart"],
    )
    run_tournament(
        generation,
        intent,
        duration=2.0,
        workspace=workspace,
        resource_finder=lambda *args, **kwargs: [],
        cloud_judge=False,
        animate_explainers=False,
    )
    from ace.utils import write_json

    write_json(generation / "visuals" / "shot-intents.json", [intent.to_dict()])
    report = validate(generation, workspace)
    assert report.unexplained_decisions == 0
    assert report.missing_count == 0
