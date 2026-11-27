"""Orchestrates a visit: PIR → capture → recognition → decision → door → owner notification.

All methods are synchronous (OpenCV is CPU-bound); FastAPI calls them in a threadpool.
"""

from __future__ import annotations

import csv
import io
import logging
import random
import threading
import time
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from backend.config import Settings
from backend.db import Database, new_id, utc_now
from backend.decision import DENIED, GRANTED, PENDING, decide
from backend.face_engine import FaceEngine, FaceError, Match, validate_name
from backend.hardware_mock import Door, MockPIR, MockRelayDriver

log = logging.getLogger(__name__)
ROLES = {"owner", "relative"}
STAGES = ["motion", "camera", "detecting", "identity", "door", "notified"]
SOURCES = {"live", "simulation"}
# Illustrated visitors used by the Project-page simulation (no real face involved).
SIM_VISITORS = {
    "owner": ("Aayush (sim)", "owner", (0.78, 0.90)),
    "relative": ("Rudrodeep (sim)", "relative", (0.70, 0.82)),
    "intruder": ("Unknown", "unknown", (0.05, 0.22)),
}
NOTIFICATION_CSV_FIELDS = ["id", "time_local", "ts", "source", "kind", "status", "title", "body", "name",
                           "role", "score", "run_id", "snapshot_id", "decided_at"]
CSV_FIELDS = ["id", "time_local", "ts", "source", "run_id", "stage", "message", "name", "role", "score", "decision", "snapshot_id"]


class NotFound(LookupError):
    pass


class Conflict(RuntimeError):
    pass


class AccessService:
    def __init__(self, settings: Settings, emit: Callable[[dict], None]):
        self.settings, self.emit = settings, emit
        self.db = Database(settings.database_path)
        self.faces = FaceEngine(settings)
        self.pir = MockPIR(settings.pir_hold_seconds)
        self.door = Door(MockRelayDriver(), settings.relay_seconds,
                         on_change=lambda status: self.emit({"type": "door", "door": status}))
        self.runs: dict[str, dict] = {}
        self._failures: deque[float] = deque(maxlen=20)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._expiry = threading.Thread(target=self._expire_loop, name="approval-expiry", daemon=True)

    def start(self) -> None:
        self.import_existing_faces()
        self.door.start()
        self._expiry.start()

    def close(self) -> None:
        self._stop.set()
        self.door.close()
        self.db.close()

    # ---- status ------------------------------------------------------------------------
    def status(self) -> dict:
        return {"door": self.door.status(), "pir_active": self.pir.active(),
                "pir_triggers": self.pir.triggers, "registry": self.db.counts(),
                "threshold": self.settings.match_threshold, "stats": self.db.stats(),
                "engine": "YuNet + SFace (OpenCV DNN)", "camera": "Laptop webcam (browser)",
                "pending_approvals": sum(1 for n in self.db.list_notifications(200)
                                         if n["status"] == "pending")}

    # ---- people & photos -----------------------------------------------------------
    def list_persons(self) -> list[dict]:
        return self.db.list_persons()

    def add_person(self, name: str, role: str) -> dict:
        if role not in ROLES:
            raise FaceError("Role must be owner or relative")
        person = self.db.add_person(validate_name(name), role)
        self.emit({"type": "registry"})
        return {**person, "photos": []}

    def update_person(self, person_id: str, role: str) -> dict:
        if role not in ROLES:
            raise FaceError("Role must be owner or relative")
        self._person(person_id)
        self.db.update_role(person_id, role)
        self.emit({"type": "registry"})
        return next(p for p in self.db.list_persons() if p["id"] == person_id)

    def delete_person(self, person_id: str) -> None:
        self._person(person_id)
        for relative_path in self.db.delete_person(person_id):
            self._safe_path(self.settings.authorized_dir, relative_path).unlink(missing_ok=True)
        self.emit({"type": "registry"})

    def add_photo(self, person_id: str, contents: bytes) -> dict:
        person = self._person(person_id)
        frame = self.faces.decode(contents)
        face = self.faces.primary_face(frame)
        folder = self.settings.authorized_dir / person["name"]
        folder.mkdir(parents=True, exist_ok=True)
        filename = f"{new_id()}.jpg"
        (folder / filename).write_bytes(self.faces.encode_jpeg(frame, 95))
        ref = self.db.add_face_ref(person_id, f"{person['name']}/{filename}", face.embedding)
        self.emit({"type": "registry"})
        return {"id": ref["id"], "person_id": person_id, "created_at": ref["created_at"],
                "image_url": f"/api/photos/{ref['id']}/image",
                "face_box": face.box}

    def photo_path(self, photo_id: str) -> Path:
        ref = self.db.get_face_ref(photo_id)
        if ref is None:
            raise NotFound("Photo not found")
        path = self._safe_path(self.settings.authorized_dir, ref["image_path"])
        if not path.is_file():
            raise NotFound("Photo file is missing")
        return path

    def delete_photo(self, photo_id: str) -> None:
        path = self.photo_path(photo_id)
        self.db.delete_face_ref(photo_id)
        path.unlink(missing_ok=True)
        self.emit({"type": "registry"})

    def snapshot_path(self, snapshot_id: str) -> Path:
        if not snapshot_id.isalnum():
            raise NotFound("Snapshot not found")
        path = self.settings.snapshots_dir / f"{snapshot_id}.jpg"
        if not path.is_file():
            raise NotFound("Snapshot not found")
        return path

    def import_existing_faces(self) -> None:
        """First start only: import photos already in authorized_faces/<Name>/ as owners."""
        if self.db.counts()["photos"]:
            return
        for folder in sorted(p for p in self.settings.authorized_dir.iterdir() if p.is_dir()):
            try:
                name = validate_name(folder.name)
            except FaceError:
                continue
            person = self.db.find_person(name) or self.db.add_person(name, "owner")
            for image in sorted(folder.glob("*")):
                if image.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                    continue
                try:
                    face = self.faces.primary_face(self.faces.decode(image.read_bytes()))
                except FaceError as exc:
                    log.warning("Skipping %s: %s", image, exc)
                    continue
                self.db.add_face_ref(person["id"], f"{folder.name}/{image.name}", face.embedding)
                log.info("Imported existing face photo for %s", name)

    # ---- visits (Test Mode runs) --------------------------------------------------------
    def create_run(self, source: str = "live") -> dict:
        if source not in SOURCES:
            raise FaceError("source must be live or simulation")
        self.pir.trigger()
        run = {"id": new_id(), "created_at": utc_now(), "stage": "camera", "decision": None,
               "identity": None, "result": None, "notification": None, "door": self.door.status(),
               "attempts": 0, "error": None, "source": source}
        with self._lock:
            self.runs[run["id"]] = run
            if len(self.runs) > 50:
                self.runs.pop(next(iter(self.runs)))
        where = "visitor entered the PIR zone" if source == "simulation" else "motion detected at the front door"
        self._event(run, "motion", f"PIR sensor HIGH: {where}, camera woken")
        self._publish_run(run)
        return run

    def get_run(self, run_id: str) -> dict:
        with self._lock:
            run = self.runs.get(run_id)
        if run is None:
            raise NotFound("Run not found; start a new one")
        return {**run, "door": self.door.status(), "events": self.db.list_events(run_id=run_id)}

    def verify(self, run_id: str, frames: list[bytes]) -> dict:
        run = self._run_for_update(run_id)
        if run["stage"] not in {"camera", "detecting"}:
            raise Conflict("This visit has already been decided; start a new run")
        if not frames:
            raise FaceError("No camera frames were received")
        run["attempts"] += 1
        self._event(run, "camera", f"Captured {len(frames)} frame(s) from the laptop camera")
        run["stage"] = "detecting"
        self._publish_run(run)

        references = self.db.references()
        observations = []  # (frame, face, match)
        for contents in frames[: self.settings.max_frames]:
            try:
                frame = self.faces.decode(contents)
            except FaceError:
                continue
            detected = self.faces.detect(frame)
            if detected:
                observations.append((frame, detected[0], self.faces.match(detected[0].embedding, references)))
        if not observations:
            run["stage"], run["error"] = "camera", "No face detected. Face the camera in good light and try again."
            self._event(run, "detecting", "No face found in the captured frames")
            self._publish_run(run)
            raise FaceError(run["error"])

        # Majority vote across frames, then the best-scoring frame for that identity.
        votes = Counter(m.person_id for _, _, m in observations)
        winner, _ = votes.most_common(1)[0]
        frame, face, match = max((o for o in observations if o[2].person_id == winner),
                                 key=lambda o: o[2].score)
        if winner is not None and votes[winner] * 2 < len(observations):
            # No majority: treat as unknown rather than letting one good frame through.
            match = Match(None, "Unknown", "unknown", match.score, False)

        snapshot_id = new_id()
        (self.settings.snapshots_dir / f"{snapshot_id}.jpg").write_bytes(
            self.faces.encode_jpeg(self.faces.annotate(frame, face, match)))
        result = {"face_found": True, "frames": len(frames), "frames_with_face": len(observations),
                  "box": face.box, "image_size": [frame.shape[1], frame.shape[0]],
                  "name": match.name, "role": match.role, "score": match.score,
                  "threshold": self.settings.match_threshold, "snapshot_id": snapshot_id,
                  "snapshot_url": f"/api/snapshots/{snapshot_id}",
                  "registered_faces": len(references)}
        run["result"], run["error"] = result, None
        self._event(run, "detecting",
                    f"Face detected in {len(observations)}/{len(frames)} frames; embedding compared with "
                    f"{len(references)} registered photo(s). Best similarity {match.score:.2f}",
                    name=match.name, role=match.role, score=match.score, snapshot_id=snapshot_id)

        return self._decide_and_notify(run, match, snapshot_id)

    def simulate(self, run_id: str, visitor: str, photo: bytes) -> dict:
        """Simulation visit: the illustrated 'photo' from the Project page replaces face recognition."""
        run = self._run_for_update(run_id)
        if run.get("source") != "simulation":
            raise Conflict("Only simulation runs can be simulated")
        if run["stage"] not in {"camera", "detecting"}:
            raise Conflict("This visit has already been decided; start a new run")
        if visitor not in SIM_VISITORS:
            raise FaceError("visitor must be owner, relative or intruder")
        frame = self.faces.decode(photo)
        name, role, (low, high) = SIM_VISITORS[visitor]
        score = round(random.uniform(low, high), 3)
        snapshot_id = new_id()
        (self.settings.snapshots_dir / f"{snapshot_id}.jpg").write_bytes(self.faces.encode_jpeg(frame))
        self._event(run, "camera", "Camera activated: photo captured of the visitor in the PIR zone",
                    snapshot_id=snapshot_id)
        authorized = role != "unknown"
        match = Match("sim-" + visitor if authorized else None, name, role, score, authorized)
        run["result"] = {"face_found": True, "frames": 1, "frames_with_face": 1, "box": [0, 0, 0, 0],
                         "image_size": [frame.shape[1], frame.shape[0]], "name": name, "role": role,
                         "score": score, "threshold": self.settings.match_threshold,
                         "snapshot_id": snapshot_id, "snapshot_url": f"/api/snapshots/{snapshot_id}",
                         "registered_faces": 0}
        self._event(run, "detecting", f"Simulated recognition: similarity {score:.2f} "
                    f"(threshold {self.settings.match_threshold:.2f})",
                    name=name, role=role, score=score, snapshot_id=snapshot_id)
        return self._decide_and_notify(run, match, snapshot_id)

    def _decide_and_notify(self, run: dict, match: Match, snapshot_id: str) -> dict:
        run_id = run["id"]
        live = run.get("source", "live") == "live"
        recent_failures = self._recent_failures() if live else 0
        decision = decide(match, self.settings.match_threshold, recent_failures)
        run["identity"], run["decision"], run["reason"] = decision.identity, decision.decision, decision.reason
        run["stage"] = "identity"
        self._event(run, "identity", {"owner": f"Identified as OWNER: {match.name}",
                                      "relative": f"Identified as RELATIVE: {match.name}",
                                      "intruder": "Unknown person: treated as INTRUDER"}[decision.identity],
                    name=match.name, role=match.role, score=match.score)
        self._event(run, "decision", decision.reason, decision=decision.decision,
                    name=match.name, role=match.role, score=match.score, snapshot_id=snapshot_id)

        common = {"run_id": run_id, "name": match.name, "role": match.role, "score": match.score,
                  "snapshot_id": snapshot_id, "source": run.get("source", "live")}
        if decision.decision == GRANTED:
            self.door.unlock(match.name)
            self._event(run, "door", f"Relay energised: door unlocked for {self.settings.relay_seconds:g}s")
            note = self.db.add_notification("info", "new", f"{match.name} entered",
                                            f"Owner recognised with similarity {match.score:.2f}. "
                                            "Door unlocked automatically.", **common)
        elif decision.decision == PENDING:
            expires = datetime.now(timezone.utc) + timedelta(seconds=self.settings.approval_seconds)
            self._event(run, "door", "Door kept locked until the owner approves")
            note = self.db.add_notification(
                "approval", "pending", f"{match.name} is at the door",
                f"Relative recognised (similarity {match.score:.2f}). Allow entry?",
                expires_at=expires.isoformat(timespec="milliseconds"), **common)
        else:
            if live:
                self._failures.append(time.monotonic())
            self._event(run, "door", "Door stays LOCKED. Snapshot stored, alert raised")
            body = f"Unrecognised visitor (best similarity {match.score:.2f})."
            if decision.repeated_attempts:
                body += f" Repeated failed attempts: {recent_failures + 1} in the last 10 minutes."
            note = self.db.add_notification("intruder", "new", "Intruder alert", body, **common)
        run["notification"] = note
        run["stage"] = "door" if decision.decision == PENDING else "notified"
        self._event(run, "notified", f"Notification sent to owner dashboard: {note['title']}")
        self.emit({"type": "notification.new", "notification": note})
        self._publish_run(run)
        return self.get_run(run_id)

    # ---- owner actions --------------------------------------------------------------------
    def list_notifications(self) -> list[dict]:
        return self.db.list_notifications()

    def clear_notifications(self, source: str | None = None) -> int:
        """Delete notifications (optionally one source). Pending approvals are denied first."""
        for note in self.db.list_notifications(100_000, source):
            if note["status"] == "pending":
                self._expire(note, reason="cleared")
        removed = self.db.clear_notifications(source)
        self.emit({"type": "notifications.cleared", "source": source})
        return removed

    def notifications_csv(self, source: str | None = None) -> str:
        return self._csv(NOTIFICATION_CSV_FIELDS, self.db.list_notifications(100_000, source))

    def decide_notification(self, notification_id: str, action: str) -> dict:
        note = self.db.get_notification(notification_id)
        if note is None:
            raise NotFound("Notification not found")
        if action == "dismiss":
            note = self.db.set_notification_status(notification_id, "read")
            self.emit({"type": "notification.updated", "notification": note})
            return note
        if note["kind"] == "info" or note["status"] not in {"pending", "new"}:
            raise Conflict("This notification has already been handled")
        if action == "block":
            return self._block(note)
        allow = action == "allow"
        note = self.db.set_notification_status(notification_id, "approved" if allow else "denied")
        if allow:
            self.door.unlock(f"{note['name']} (owner approved)")
        run = self.runs.get(note["run_id"] or "")
        message = (f"Owner {'ALLOWED' if allow else 'DENIED'} entry for {note['name']}"
                   + ("; door unlocked" if allow else "; door stays locked"))
        if run is not None:
            with self._lock:
                run["decision"] = GRANTED if allow else DENIED
                run["reason"] = message
                run["stage"] = "notified"
                run["notification"] = note
            self._event(run, "decision", message, decision=run["decision"], name=note["name"],
                        role=note["role"], score=note["score"])
            self._publish_run(run)
        else:
            event = self.db.add_event("decision", message, note["run_id"], decision=GRANTED if allow else DENIED,
                                      name=note["name"], role=note["role"], score=note["score"],
                                      source=note.get("source") or "live")
            self.emit({"type": "event", "event": event})
        self.emit({"type": "notification.updated", "notification": note})
        return note

    def _block(self, note: dict) -> dict:
        """Owner chose to block the door for an intruder: force-lock and record it."""
        if note["kind"] != "intruder":
            raise Conflict("Only intruder alerts can be blocked; use Deny for approval requests")
        note = self.db.set_notification_status(note["id"], "blocked")
        self.door.lock()
        message = "Owner BLOCKED the door for the intruder; door locked"
        self._note_event(note, "door", message, decision=DENIED)
        self.emit({"type": "notification.updated", "notification": note})
        return note

    def emergency(self, notification_id: str, action: str) -> dict:
        """Emergency response from an intruder alert. Calls are simulated and logged (prototype)."""
        note = self.db.get_notification(notification_id)
        if note is None:
            raise NotFound("Notification not found")
        if note["kind"] != "intruder":
            raise Conflict("Emergency actions are only available for intruder alerts")
        if action not in {"police", "siren"}:
            raise FaceError("action must be police or siren")
        if action == "police":
            message = "Owner called the POLICE (112) about the intruder at the front door [simulated call]"
        else:
            message = "Owner sounded the SIREN at the front door"
            self.emit({"type": "siren", "notification_id": notification_id})
        note = self.db.add_emergency(notification_id, action)
        self._note_event(note, "emergency", message)
        self.emit({"type": "notification.updated", "notification": note})
        return note

    def _note_event(self, note: dict, stage: str, message: str, decision: str | None = None) -> None:
        run = self.runs.get(note["run_id"] or "")
        fields = {"name": note["name"], "role": note["role"], "score": note["score"], "decision": decision}
        if run is not None:
            with self._lock:
                run["reason"], run["notification"] = message, note
            self._event(run, stage, message, **fields)
            self._publish_run(run)
        else:
            event = self.db.add_event(stage, message, note["run_id"], source=note.get("source") or "live", **fields)
            self.emit({"type": "event", "event": event})

    def lock_door(self) -> dict:
        self.door.lock()
        self.emit({"type": "event", "event": self.db.add_event("door", "Owner locked the door manually")})
        return self.door.status()

    def list_events(self, limit: int, source: str | None = None) -> list[dict]:
        return self.db.list_events(limit=limit, source=source)

    def clear_events(self, source: str | None = None) -> int:
        removed = self.db.clear_events(source)
        self.emit({"type": "events.cleared", "source": source})
        return removed

    def events_csv(self, source: str | None = None) -> str:
        return self._csv(CSV_FIELDS, self.db.list_events(limit=100_000, source=source))

    @staticmethod
    def _csv(fields: list[str], rows_newest_first: list[dict]) -> str:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in reversed(rows_newest_first):  # oldest first reads naturally in a spreadsheet
            local = datetime.fromisoformat(row["ts"]).astimezone()
            writer.writerow({**row, "time_local": local.strftime("%Y-%m-%d %H:%M:%S")})
        return buffer.getvalue()

    # ---- internals ----------------------------------------------------------------------
    def _expire_loop(self) -> None:
        while not self._stop.wait(1.0):
            now = utc_now()
            try:
                for note in self.db.list_notifications(200):
                    if note["status"] == "pending" and note["expires_at"] and note["expires_at"] < now:
                        self._expire(note)
            except Exception:  # keep the loop alive; the next tick retries
                log.exception("Approval expiry check failed")

    def _expire(self, note: dict, reason: str = "timeout") -> None:
        note = self.db.set_notification_status(note["id"], "expired")
        run = self.runs.get(note["run_id"] or "")
        message = (f"Owner cleared notifications; request for {note['name']} denied and the door stays locked"
                   if reason == "cleared" else
                   f"No owner response for {note['name']}; request expired and the door stays locked")
        if run is not None:
            with self._lock:
                run.update(decision=DENIED, reason=message, stage="notified", notification=note)
            self._event(run, "decision", message, decision=DENIED, name=note["name"], role=note["role"])
            self._publish_run(run)
        self.emit({"type": "notification.updated", "notification": note})

    def _recent_failures(self) -> int:
        cutoff = time.monotonic() - 600
        return sum(1 for t in self._failures if t >= cutoff)

    def _person(self, person_id: str) -> dict:
        person = self.db.get_person(person_id)
        if person is None:
            raise NotFound("Person not found")
        return person

    def _run_for_update(self, run_id: str) -> dict:
        with self._lock:
            run = self.runs.get(run_id)
        if run is None:
            raise NotFound("Run not found; start a new one")
        return run

    def _event(self, run: dict, stage: str, message: str, **fields) -> None:
        event = self.db.add_event(stage, message, run["id"], source=run.get("source", "live"), **fields)
        self.emit({"type": "event", "event": event})

    def _publish_run(self, run: dict) -> None:
        self.emit({"type": "run.update", "run": {**run, "door": self.door.status()}})

    @staticmethod
    def _safe_path(root: Path, relative: str) -> Path:
        path = (root / relative.replace("\\", "/")).resolve()
        if root.resolve() not in path.parents:
            raise NotFound("Invalid path")
        return path
