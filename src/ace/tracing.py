from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any

from ace.paths import resolve_paths
from ace.utils import ensure_dir, utc_now_iso


_LOCK = threading.Lock()


def new_trace_id(prefix: str = "trace") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


def trace_path(workspace: str | Path | None = None) -> Path:
    return ensure_dir(resolve_paths(workspace).cache_root / "traces") / "provider-events.jsonl"


def emit(
    event: str,
    *,
    workspace: str | Path | None = None,
    trace_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    **fields: Any,
) -> dict[str, Any]:
    row = {
        "timestamp": utc_now_iso(),
        "event": event,
        "trace_id": trace_id or new_trace_id(),
        "metadata": metadata or {},
        **fields,
    }
    path = trace_path(workspace)
    with _LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    return row


def read_recent(workspace: str | Path | None = None, limit: int = 100) -> list[dict[str, Any]]:
    path = trace_path(workspace)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-max(1, limit):]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows
