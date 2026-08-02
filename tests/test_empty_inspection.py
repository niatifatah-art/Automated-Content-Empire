from ace.captions import inspect as inspect_captions
from ace.editing import inspect as inspect_editing
from ace.visuals import inspect as inspect_visuals


def test_empty_generation_is_not_reported_as_passed(generation, workspace):
    assert inspect_captions(generation, workspace)["status"] == "not_run"
    assert inspect_visuals(generation, workspace)["status"] == "not_run"
    assert inspect_editing(generation, workspace)["status"] == "not_run"
