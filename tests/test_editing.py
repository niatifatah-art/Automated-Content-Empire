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
