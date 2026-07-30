from pathlib import Path

from ace.visual_intelligence.contracts import ShotIntent
from ace.visual_intelligence.explainer import render_explainer


def test_network_explainer_is_original_and_semantic(tmp_path: Path):
    intent = ShotIntent(
        shot_id="shot-004",
        narration="If the network lacks encryption, traffic may be exposed.",
        purpose="explain_mechanism",
        subject="unencrypted_network_traffic",
        preferred_formats=["animated_explainer"],
        required_elements=["shared_access_point", "multiple_devices", "data_packets", "missing_encryption_lock"],
    )
    result = render_explainer(intent, tmp_path, animate=False)
    assert result.path.exists()
    assert result.path.suffix == ".png"
    assert result.path.stat().st_size > 10_000
    assert set(intent.required_elements).issubset(set(result.semantic_elements))


def test_terminal_and_phone_hotspot_resolve_to_specific_formats(tmp_path: Path):
    terminal = ShotIntent(
        shot_id="shot-terminal",
        narration="Run sudo apt update in the terminal.",
        purpose="demonstrate",
        subject="linux_terminal_command",
        preferred_formats=["terminal_demo", "kinetic_typography"],
        required_elements=["terminal", "exact_command", "visible_result"],
        metadata={"command": "sudo apt update"},
    )
    terminal_result = render_explainer(terminal, tmp_path, animate=False, visual_format="terminal_demo")
    assert terminal_result.visual_format == "terminal_demo"
    assert terminal_result.path.exists()

    hotspot = ShotIntent(
        shot_id="shot-hotspot",
        narration="Use your phone's personal hotspot.",
        purpose="demonstrate",
        subject="phone_personal_hotspot",
        preferred_formats=["application_demo", "stock_video"],
        required_elements=["smartphone", "hotspot_settings", "connected_device"],
    )
    hotspot_result = render_explainer(hotspot, tmp_path, animate=False, visual_format="application_demo")
    assert hotspot_result.visual_format == "application_demo"
    assert hotspot_result.path.exists()
