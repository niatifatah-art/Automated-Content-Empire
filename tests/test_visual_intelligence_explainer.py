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


def test_dns_browser_demo_never_uses_phone_hotspot_template(tmp_path: Path):
    intent = ShotIntent(
        shot_id="shot-dns",
        narration="The browser asks DNS for the IP address behind example.com.",
        purpose="explain_mechanism",
        subject="browser_dns_lookup",
        preferred_formats=["browser_demo", "animated_explainer"],
        required_elements=["browser_address_bar", "domain_name", "dns_resolver", "ip_address"],
    )
    result = render_explainer(intent, tmp_path, animate=False, visual_format="browser_demo")
    assert result.visual_format == "browser_demo"
    assert "DNS" in result.description or "domain" in result.description.lower()
    assert "hotspot_settings" not in result.semantic_elements
    assert {"dns_resolver", "domain_name", "ip_address"}.issubset(set(result.semantic_elements))


def test_generic_application_demo_is_neutral(tmp_path: Path):
    intent = ShotIntent(
        shot_id="shot-settings",
        narration="Open the app settings and enable the privacy option.",
        purpose="demonstrate",
        subject="application_privacy_settings",
        preferred_formats=["application_demo"],
        required_elements=["relevant_interface", "visible_action"],
    )
    result = render_explainer(intent, tmp_path, animate=False, visual_format="application_demo")
    assert result.visual_format == "application_demo"
    assert "neutral application" in result.description.lower()
    assert "hotspot_settings" not in result.semantic_elements


def test_code_logic_is_not_mislabeled_as_application_demo(tmp_path: Path):
    intent = ShotIntent(
        shot_id="shot-code",
        narration="This Python loop mutates the list while iterating.",
        purpose="explain_mechanism",
        subject="python_list_mutation",
        preferred_formats=["animated_explainer", "terminal_demo"],
        required_elements=["code_state", "before_after", "execution_flow"],
    )
    result = render_explainer(intent, tmp_path, animate=False, visual_format="animated_explainer")
    assert result.visual_format == "animated_explainer"
    assert "code-flow" in result.description.lower()


def test_url_hook_prefers_browser_action_over_title_card():
    from ace.visual_intelligence.intent import deterministic_intent

    intent = deterministic_intent(
        "You type a URL and press Enter.",
        shot_id="shot-hook",
        purpose="hook",
        mood="technical_dynamic",
        topic="What happens after you type a URL",
    )
    assert intent.preferred_formats[0] in {"browser_demo", "stock_video", "animated_explainer"}
    assert intent.preferred_formats[0] != "kinetic_typography"
