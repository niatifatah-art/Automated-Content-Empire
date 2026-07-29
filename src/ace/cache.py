from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from ace.paths import resolve_paths
from ace.utils import sha256_bytes


class Cache:
    def __init__(self, workspace: str | Path | None = None):
        self.path = resolve_paths(workspace).cache_db
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS cache_entries ("
                "cache_key TEXT PRIMARY KEY, created REAL NOT NULL, expires REAL NOT NULL, value TEXT NOT NULL)"
            )

    @staticmethod
    def key(namespace: str, value: str) -> str:
        return f"{namespace}:{sha256_bytes(value.encode('utf-8'))}"

    def get(self, key: str) -> Any | None:
        now = time.time()
        with self._connection() as connection:
            row = connection.execute(
                "SELECT value, expires FROM cache_entries WHERE cache_key = ?", (key,)
            ).fetchone()
            if not row:
                return None
            if float(row[1]) < now:
                connection.execute("DELETE FROM cache_entries WHERE cache_key = ?", (key,))
                return None
            try:
                return json.loads(row[0])
            except json.JSONDecodeError:
                return None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        now = time.time()
        payload = json.dumps(value, ensure_ascii=False)
        with self._connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO cache_entries(cache_key, created, expires, value) VALUES (?, ?, ?, ?)",
                (key, now, now + max(1, ttl_seconds), payload),
            )

    def purge_expired(self) -> int:
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM cache_entries WHERE expires < ?", (time.time(),))
            return int(cursor.rowcount)
