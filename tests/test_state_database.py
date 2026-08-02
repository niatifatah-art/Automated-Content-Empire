from pathlib import Path

from ace.state import approve, event, set_overall, set_stage, summary


def test_generation_state_is_persistent(generation: Path):
    set_stage(generation, "visual_intelligence", "running", detail="Planning shots")
    set_stage(generation, "visual_intelligence", "passed", detail="Selected visuals")
    event(generation, "visual_replaced", stage="visual_intelligence", status="passed", metadata={"shot_id": "shot-004"})
    approve(generation, "visual_intelligence", subject_id="shot-004")
    set_overall(generation, "COMPLETE_WITH_WARNINGS")
    report = summary(generation)
    assert report["generation"]["overall_status"] == "COMPLETE_WITH_WARNINGS"
    assert report["stages"][0]["name"] == "visual_intelligence"
    assert report["stages"][0]["attempt"] == 1
    assert report["approvals"][0]["subject_id"] == "shot-004"
    assert any(item["kind"] == "visual_replaced" for item in report["events"])
