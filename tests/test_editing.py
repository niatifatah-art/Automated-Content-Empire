from ace.captions import plan as plan_captions
from ace.editing import create_package, render, validate_media
from ace.graphics import create_card
from ace.utils import write_json
from ace.visuals import plan as plan_visuals
from ace.voice import create_test_tone, prepare


def test_offline_preview_render(generation, workspace):
    prepare(generation, workspace)
    create_test_tone(generation / "voice" / "narration.wav", duration=10)
    plan_captions(generation, workspace)
    shots = plan_visuals(generation, workspace)
    for shot in shots:
        card = generation / "visuals" / "generated" / f"card-{shot.index}.png"
        create_card(card, title=shot.narration, label="TEST", footer="ACE generated visual")
        shot.resource_path = str(card)
        shot.resource_id = f"card-{shot.index}"
        shot.visual_type = "generated_graphic"
    write_json(generation / "visuals" / "shot-plan.json", [shot.__dict__ for shot in shots])
    create_package(generation, workspace)
    output = render(generation, workspace, preview=True)
    report = validate_media(output, generation=generation, workspace=workspace, expect_audio=True)
    assert output.exists()
    assert report["status"] in {"passed", "warning"}
    assert report["width"] == 360
    assert report["height"] == 640


def test_preview_render_supports_secondary_visual_overlay(generation, workspace):
    prepare(generation, workspace)
    create_test_tone(generation / "voice" / "narration.wav", duration=10)
    plan_captions(generation, workspace)
    shots = plan_visuals(generation, workspace)
    for shot in shots:
        primary = generation / "visuals" / "generated" / f"primary-{shot.index}.png"
        secondary = generation / "visuals" / "generated" / f"secondary-{shot.index}.png"
        create_card(primary, title=shot.narration, label="PRIMARY", footer="ACE")
        create_card(secondary, title="Supporting B-roll", label="SECONDARY", footer="ACE")
        shot.resource_path = str(primary)
        shot.resource_id = f"primary-{shot.index}"
        shot.visual_type = "animated_explainer"
        shot.duration = max(3.0, shot.duration)
        shot.metadata.setdefault("creative", {})["overlay"] = "callout"
        shot.metadata["secondary_visual"] = {"path": str(secondary), "format": "browser_demo"}
        shot.metadata["secondary_usage"] = {"mode": "pip", "start": 0.5, "duration": 1.0}
    write_json(generation / "visuals" / "shot-plan.json", [shot.__dict__ for shot in shots])
    create_package(generation, workspace)
    output = render(generation, workspace, preview=True)
    assert output.exists()
