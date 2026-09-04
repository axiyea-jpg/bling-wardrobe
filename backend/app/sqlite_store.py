from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any

from .settings import settings


class SqliteUserStore:
    """Small local, user-scoped JSON document store backed by SQLite."""

    def __init__(self, collection: str):
        self.collection = collection
        self.lock = RLock()

    @property
    def path(self) -> Path:
        return settings.data_dir / "bling-wardrobe.sqlite3"

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS documents (
                collection TEXT NOT NULL,
                user_id TEXT NOT NULL,
                id TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (collection, user_id, id)
            )"""
        )
        return connection

    def list(self, uid: str) -> list[dict[str, Any]]:
        with self.lock, self._connect() as db:
            rows = db.execute(
                "SELECT payload FROM documents WHERE collection=? AND user_id=? ORDER BY updated_at, id",
                (self.collection, uid),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def get(self, uid: str, key: str) -> dict[str, Any] | None:
        with self.lock, self._connect() as db:
            row = db.execute(
                "SELECT payload FROM documents WHERE collection=? AND user_id=? AND id=?",
                (self.collection, uid, key),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, uid: str, key: str, value: dict[str, Any]) -> None:
        payload = dict(value, id=key, user_id=uid)
        with self.lock, self._connect() as db:
            db.execute(
                """INSERT INTO documents(collection,user_id,id,payload,updated_at)
                   VALUES(?,?,?,?,CURRENT_TIMESTAMP)
                   ON CONFLICT(collection,user_id,id) DO UPDATE SET
                   payload=excluded.payload, updated_at=CURRENT_TIMESTAMP""",
                (self.collection, uid, key, json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
            )

    def delete(self, uid: str, key: str) -> None:
        with self.lock, self._connect() as db:
            db.execute(
                "DELETE FROM documents WHERE collection=? AND user_id=? AND id=?",
                (self.collection, uid, key),
            )

