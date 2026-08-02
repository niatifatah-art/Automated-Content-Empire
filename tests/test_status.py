from ace.status import inspect
from ace.utils import write_json


def test_warning_script_above_threshold_is_not_incomplete(generation, workspace):
    write_json(generation / "quality" / "script-report.json", {"status": "warning", "score": 98, "critical": [], "warnings": ["minor"]})
    write_json(generation / "quality" / "fact-report.json", {"status": "warning", "critical": [], "source_count": 2, "claim_count": 1, "verified_count": 1})
    # Change to non-video so only script/fact are required.
    meta = __import__("json").loads((generation / "metadata.json").read_text())
    meta["content_type"] = "post"
    write_json(generation / "metadata.json", meta)
    report = inspect(generation, workspace)
    assert report["overall"] == "COMPLETE_WITH_WARNINGS"
    assert report["stages"]["script_quality"]["ok"] is True
