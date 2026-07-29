from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ace.storage import metadata, resolve_generation
from ace.utils import read_json, utc_now_iso, write_json


def prepare(generation: str | Path, workspace: str | Path | None = None) -> dict[str, Any]:
    folder = resolve_generation(generation, workspace)
    final = folder / "exports" / "final.mp4"
    if not final.exists():
        raise FileNotFoundError("Final video is missing.")
    meta = metadata(folder)
    record = {
        "status": "prepared",
        "generation": str(folder),
        "platform": meta.get("platform"),
        "content_type": meta.get("content_type"),
        "title": meta.get("topic"),
        "media": str(final),
        "prepared_at": utc_now_iso(),
        "approved": False,
        "scheduled_for": None,
        "automatic_publish": False,
        "note": "ACE 2.0 never publishes automatically. Human approval is required before scheduling.",
    }
    write_json(folder / "publishing" / "publish-plan.json", record)
    return record


def approve(generation: str | Path, workspace: str | Path | None = None) -> dict[str, Any]:
    folder = resolve_generation(generation, workspace)
    path = folder / "publishing" / "publish-plan.json"
    record = read_json(path, None)
    if not isinstance(record, dict):
        record = prepare(folder, workspace)
    record.update({"approved": True, "approved_at": utc_now_iso(), "status": "approved"})
    write_json(path, record)
    return record


def schedule(generation: str | Path, when: str, workspace: str | Path | None = None) -> dict[str, Any]:
    folder = resolve_generation(generation, workspace)
    path = folder / "publishing" / "publish-plan.json"
    record = read_json(path, None)
    if not isinstance(record, dict):
        record = prepare(folder, workspace)
    if not record.get("approved"):
        raise PermissionError("Approve the final generation before scheduling it.")
    try:
        datetime.fromisoformat(when.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Use an ISO date/time, for example 2026-08-01T18:00:00+01:00") from exc
    record.update({"scheduled_for": when, "status": "scheduled", "scheduled_at": utc_now_iso()})
    write_json(path, record)
    return record
