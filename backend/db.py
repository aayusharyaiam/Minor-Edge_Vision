"""SQLite storage: people, face references (embeddings), events and owner notifications."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS persons (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    role TEXT NOT NULL CHECK (role IN ('owner', 'relative')),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS face_refs (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    image_path TEXT NOT NULL,
    embedding BLOB NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    run_id TEXT,
    stage TEXT NOT NULL,
    message TEXT NOT NULL,
    name TEXT,
    role TEXT,
    score REAL,
    decision TEXT,
    snapshot_id TEXT
);
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    run_id TEXT,
    kind TEXT NOT NULL CHECK (kind IN ('intruder', 'approval', 'info')),
    status TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    name TEXT,
    role TEXT,
    score REAL,
    snapshot_id TEXT,
    expires_at TEXT,
    decided_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_notifications_ts ON notifications(ts);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_id() -> str:
    return uuid.uuid4().hex


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        for table in ("events", "notifications"):  # migrate databases created before 'source' existed
            columns = {row[1] for row in self.conn.execute(f"PRAGMA table_info({table})")}
            if "source" not in columns:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN source TEXT NOT NULL DEFAULT 'live'")
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(notifications)")}
        if "emergency" not in columns:  # comma-separated emergency actions taken, e.g. "police,siren"
            self.conn.execute("ALTER TABLE notifications ADD COLUMN emergency TEXT")

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def _all(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(row) for row in self.conn.execute(sql, params).fetchall()]

    def _one(self, sql: str, params: tuple = ()) -> dict | None:
        with self._lock:
            row = self.conn.execute(sql, params).fetchone()
            return dict(row) if row else None

    def _run(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self.conn.execute(sql, params)

    # ---- persons -------------------------------------------------------------------
    def add_person(self, name: str, role: str) -> dict:
        person = {"id": new_id(), "name": name, "role": role, "created_at": utc_now()}
        try:
            self._run("INSERT INTO persons (id, name, role, created_at) VALUES (?, ?, ?, ?)",
                      (person["id"], name, role, person["created_at"]))
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"A person named {name!r} is already registered") from exc
        return person

    def get_person(self, person_id: str) -> dict | None:
        return self._one("SELECT * FROM persons WHERE id = ?", (person_id,))

    def find_person(self, name: str) -> dict | None:
        return self._one("SELECT * FROM persons WHERE name = ?", (name,))

    def list_persons(self) -> list[dict]:
        persons = self._all("SELECT * FROM persons ORDER BY role, name")
        photos = self._all("SELECT id, person_id, created_at FROM face_refs ORDER BY created_at")
        for person in persons:
            person["photos"] = [{"id": p["id"], "created_at": p["created_at"],
                                 "image_url": f"/api/photos/{p['id']}/image"}
                                for p in photos if p["person_id"] == person["id"]]
        return persons

    def update_role(self, person_id: str, role: str) -> None:
        self._run("UPDATE persons SET role = ? WHERE id = ?", (role, person_id))

    def delete_person(self, person_id: str) -> list[str]:
        paths = [r["image_path"] for r in self._all(
            "SELECT image_path FROM face_refs WHERE person_id = ?", (person_id,))]
        self._run("DELETE FROM persons WHERE id = ?", (person_id,))
        return paths

    # ---- face references -------------------------------------------------------------
    def add_face_ref(self, person_id: str, image_path: str, embedding: np.ndarray) -> dict:
        ref = {"id": new_id(), "person_id": person_id, "image_path": image_path, "created_at": utc_now()}
        self._run("INSERT INTO face_refs (id, person_id, image_path, embedding, created_at) VALUES (?, ?, ?, ?, ?)",
                  (ref["id"], person_id, image_path, embedding.astype(np.float32).tobytes(), ref["created_at"]))
        return ref

    def get_face_ref(self, ref_id: str) -> dict | None:
        return self._one("SELECT id, person_id, image_path, created_at FROM face_refs WHERE id = ?", (ref_id,))

    def delete_face_ref(self, ref_id: str) -> None:
        self._run("DELETE FROM face_refs WHERE id = ?", (ref_id,))

    def references(self) -> list[dict]:
        rows = self._all("""SELECT f.person_id, f.embedding, p.name, p.role
                            FROM face_refs f JOIN persons p ON p.id = f.person_id""")
        for row in rows:
            row["embedding"] = np.frombuffer(row["embedding"], dtype=np.float32)
        return rows

    def counts(self) -> dict:
        row = self._one("""SELECT
            (SELECT COUNT(*) FROM persons WHERE role='owner') AS owners,
            (SELECT COUNT(*) FROM persons WHERE role='relative') AS relatives,
            (SELECT COUNT(*) FROM face_refs) AS photos""")
        return row or {"owners": 0, "relatives": 0, "photos": 0}

    # ---- events ---------------------------------------------------------------------
    def add_event(self, stage: str, message: str, run_id: str | None = None, **fields) -> dict:
        event = {"ts": utc_now(), "run_id": run_id, "source": fields.get("source") or "live",
                 "stage": stage, "message": message,
                 "name": fields.get("name"), "role": fields.get("role"), "score": fields.get("score"),
                 "decision": fields.get("decision"), "snapshot_id": fields.get("snapshot_id")}
        cursor = self._run(
            "INSERT INTO events (ts, run_id, source, stage, message, name, role, score, decision, snapshot_id)"
            " VALUES (:ts, :run_id, :source, :stage, :message, :name, :role, :score, :decision, :snapshot_id)",
            event)
        return {"id": cursor.lastrowid, **event}

    def list_events(self, limit: int = 100, run_id: str | None = None, source: str | None = None) -> list[dict]:
        if run_id:
            return self._all("SELECT * FROM events WHERE run_id = ? ORDER BY id", (run_id,))
        if source:
            return self._all("SELECT * FROM events WHERE source = ? ORDER BY id DESC LIMIT ?", (source, limit))
        return self._all("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))

    def clear_events(self, source: str | None = None) -> int:
        if source:
            return self._run("DELETE FROM events WHERE source = ?", (source,)).rowcount
        return self._run("DELETE FROM events").rowcount

    def stats(self) -> dict:
        row = self._one("""SELECT
            SUM(decision='GRANTED') AS granted, SUM(decision='DENIED') AS denied,
            SUM(decision='PENDING') AS pending, COUNT(DISTINCT run_id) AS visits
            FROM events WHERE stage='decision'""")
        return {k: int(v or 0) for k, v in (row or {}).items()}

    # ---- notifications -------------------------------------------------------------------
    def add_notification(self, kind: str, status: str, title: str, body: str, **fields) -> dict:
        item = {"id": new_id(), "ts": utc_now(), "kind": kind, "status": status, "title": title,
                "body": body, "run_id": fields.get("run_id"), "name": fields.get("name"),
                "role": fields.get("role"), "score": fields.get("score"),
                "snapshot_id": fields.get("snapshot_id"), "expires_at": fields.get("expires_at"),
                "decided_at": None, "source": fields.get("source") or "live"}
        self._run("""INSERT INTO notifications (id, ts, run_id, kind, status, title, body, name, role,
                     score, snapshot_id, expires_at, decided_at, source) VALUES (:id, :ts, :run_id, :kind,
                     :status, :title, :body, :name, :role, :score, :snapshot_id, :expires_at, :decided_at,
                     :source)""",
                  item)
        return item

    def get_notification(self, notification_id: str) -> dict | None:
        return self._one("SELECT * FROM notifications WHERE id = ?", (notification_id,))

    def list_notifications(self, limit: int = 50, source: str | None = None) -> list[dict]:
        if source:
            return self._all("SELECT * FROM notifications WHERE source = ? ORDER BY ts DESC LIMIT ?", (source, limit))
        return self._all("SELECT * FROM notifications ORDER BY ts DESC LIMIT ?", (limit,))

    def set_notification_status(self, notification_id: str, status: str) -> dict | None:
        self._run("UPDATE notifications SET status = ?, decided_at = ? WHERE id = ?",
                  (status, utc_now(), notification_id))
        return self.get_notification(notification_id)

    def add_emergency(self, notification_id: str, action: str) -> dict | None:
        note = self.get_notification(notification_id)
        if note is None:
            return None
        actions = [a for a in (note.get("emergency") or "").split(",") if a]
        if action not in actions:
            actions.append(action)
        self._run("UPDATE notifications SET emergency = ? WHERE id = ?", (",".join(actions), notification_id))
        return self.get_notification(notification_id)

    def clear_notifications(self, source: str | None = None) -> int:
        if source:
            return self._run("DELETE FROM notifications WHERE source = ?", (source,)).rowcount
        return self._run("DELETE FROM notifications").rowcount

    def mark_all_read(self) -> None:
        self._run("UPDATE notifications SET status = 'read' WHERE status = 'new'")

