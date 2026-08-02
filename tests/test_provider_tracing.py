from pathlib import Path

from ace.tracing import emit, read_recent


def test_trace_events_are_persisted(workspace: Path):
    emit("model.attempt.start", workspace=workspace, trace_id="trace-test", metadata={"shot_id": "shot-001"}, provider="gemini")
    rows = read_recent(workspace, limit=5)
    assert rows[-1]["trace_id"] == "trace-test"
    assert rows[-1]["metadata"]["shot_id"] == "shot-001"
