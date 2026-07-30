from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def db_path(folder: str | Path) -> Path:
    return Path(folder) / "state" / "generation.sqlite3"


def connect(folder: str | Path) -> sqlite3.Connection:
    path = db_path(folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    _migrate(connection)
    return connection


def _migrate(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS generation (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            overall_status TEXT NOT NULL DEFAULT 'created',
            current_stage TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS stages (
            name TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            attempt INTEGER NOT NULL DEFAULT 0,
            detail TEXT,
            artifact_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            stage TEXT,
            kind TEXT NOT NULL,
            status TEXT,
            message TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            stage TEXT NOT NULL,
            subject_id TEXT,
            decision TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT 'user',
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_events_stage ON events(stage, id);
        CREATE INDEX IF NOT EXISTS idx_approvals_stage ON approvals(stage, id);
        """
    )
    now = _now()
    connection.execute(
        "INSERT OR IGNORE INTO generation(id, created_at, updated_at, overall_status) VALUES(1, ?, ?, 'created')",
        (now, now),
    )
    connection.commit()


def initialize(folder: str | Path, metadata: dict[str, Any] | None = None) -> Path:
    with connect(folder) as connection:
        if metadata:
            connection.execute(
                "UPDATE generation SET updated_at=?, metadata_json=? WHERE id=1",
                (_now(), json.dumps(metadata, ensure_ascii=False)),
            )
            connection.commit()
    return db_path(folder)


def event(
    folder: str | Path,
    kind: str,
    *,
    stage: str | None = None,
    status: str | None = None,
    message: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    with connect(folder) as connection:
        connection.execute(
            "INSERT INTO events(created_at, stage, kind, status, message, metadata_json) VALUES(?,?,?,?,?,?)",
            (_now(), stage, kind, status, message, json.dumps(metadata or {}, ensure_ascii=False)),
        )
        connection.execute(
            "UPDATE generation SET updated_at=?, current_stage=COALESCE(?, current_stage) WHERE id=1",
            (_now(), stage),
        )
        connection.commit()


def set_stage(
    folder: str | Path,
    name: str,
    status: str,
    *,
    detail: str = "",
    artifact: dict[str, Any] | None = None,
) -> None:
    now = _now()
    with connect(folder) as connection:
        existing = connection.execute("SELECT attempt, started_at FROM stages WHERE name=?", (name,)).fetchone()
        attempt = int(existing["attempt"]) if existing else 0
        started_at = existing["started_at"] if existing else None
        if status == "running":
            attempt += 1
            started_at = now
        finished_at = now if status in {"passed", "warning", "failed", "skipped"} else None
        connection.execute(
            """
            INSERT INTO stages(name, status, started_at, finished_at, attempt, detail, artifact_json)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(name) DO UPDATE SET
              status=excluded.status,
              started_at=COALESCE(excluded.started_at, stages.started_at),
              finished_at=excluded.finished_at,
              attempt=excluded.attempt,
              detail=excluded.detail,
              artifact_json=excluded.artifact_json
            """,
            (name, status, started_at, finished_at, attempt, detail, json.dumps(artifact or {}, ensure_ascii=False)),
        )
        connection.execute(
            "UPDATE generation SET updated_at=?, current_stage=?, overall_status=? WHERE id=1",
            (now, name, "failed" if status == "failed" else "running" if status == "running" else "in_progress"),
        )
        connection.commit()
    event(folder, "stage", stage=name, status=status, message=detail, metadata=artifact)


@contextmanager
def stage(folder: str | Path, name: str, *, detail: str = "") -> Iterator[None]:
    set_stage(folder, name, "running", detail=detail)
    try:
        yield
    except Exception as exc:
        set_stage(folder, name, "failed", detail=str(exc))
        raise
    else:
        set_stage(folder, name, "passed", detail=detail or "Stage completed.")


def approve(
    folder: str | Path,
    stage_name: str,
    *,
    subject_id: str | None = None,
    decision: str = "approved",
    actor: str = "user",
    metadata: dict[str, Any] | None = None,
) -> None:
    with connect(folder) as connection:
        connection.execute(
            "INSERT INTO approvals(created_at, stage, subject_id, decision, actor, metadata_json) VALUES(?,?,?,?,?,?)",
            (_now(), stage_name, subject_id, decision, actor, json.dumps(metadata or {}, ensure_ascii=False)),
        )
        connection.commit()
    event(folder, "approval", stage=stage_name, status=decision, message=f"{actor}: {decision}", metadata={"subject_id": subject_id, **(metadata or {})})


def set_overall(folder: str | Path, status: str, *, metadata: dict[str, Any] | None = None) -> None:
    with connect(folder) as connection:
        current = connection.execute("SELECT metadata_json FROM generation WHERE id=1").fetchone()
        values = json.loads(current["metadata_json"] or "{}") if current else {}
        values.update(metadata or {})
        connection.execute(
            "UPDATE generation SET updated_at=?, overall_status=?, metadata_json=? WHERE id=1",
            (_now(), status, json.dumps(values, ensure_ascii=False)),
        )
        connection.commit()


def summary(folder: str | Path, *, event_limit: int = 50) -> dict[str, Any]:
    with connect(folder) as connection:
        generation = connection.execute("SELECT * FROM generation WHERE id=1").fetchone()
        stages = connection.execute("SELECT * FROM stages ORDER BY rowid").fetchall()
        events = connection.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (event_limit,)).fetchall()
        approvals = connection.execute("SELECT * FROM approvals ORDER BY id DESC").fetchall()
    def row(item: sqlite3.Row) -> dict[str, Any]:
        output = dict(item)
        for key in ("metadata_json", "artifact_json"):
            if key in output:
                output[key.removesuffix("_json")] = json.loads(output.pop(key) or "{}")
        return output
    return {
        "generation": row(generation) if generation else {},
        "stages": [row(item) for item in stages],
        "events": [row(item) for item in events],
        "approvals": [row(item) for item in approvals],
        "database": str(db_path(folder)),
    }
