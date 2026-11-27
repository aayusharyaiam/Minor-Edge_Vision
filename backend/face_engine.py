"""Face detection (YuNet) + face embeddings (SFace) with cosine-similarity matching.

Embeddings, not raw images, are compared. Each reference photo is embedded once
when it is uploaded and the 128-d vector is stored in SQLite.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field

import cv2
import numpy as np

from backend.config import Settings

NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,49}\Z")
RESERVED_NAMES = {"unknown", "admin", "system", "intruder"}
JPEG_MAGIC, PNG_MAGIC = b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n"


class FaceError(ValueError):
    """A user-facing problem with an uploaded image."""


@dataclass
class DetectedFace:
    box: tuple[int, int, int, int]
    score: float
    embedding: np.ndarray = field(repr=False)


@dataclass
class Match:
    person_id: str | None
    name: str
    role: str  # owner | relative | unknown
    score: float  # cosine similarity, -1..1
    authorized: bool


def validate_name(name: str) -> str:
    name = name.strip()
    if not NAME_PATTERN.fullmatch(name):
        raise FaceError("Use 1-50 characters: letters, numbers, spaces, dots, hyphens or underscores")
    if name.lower() in RESERVED_NAMES:
        raise FaceError("That name is reserved by the system")
    return name


class FaceEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        for path in (settings.detector_model, settings.recognizer_model):
            if not path.is_file():
                raise RuntimeError(f"Missing model {path.name}. Run: python scripts/download_models.py")
        self._lock = threading.Lock()
        self.detector = cv2.FaceDetectorYN.create(
            str(settings.detector_model), "", (320, 320), settings.detection_score, 0.3, 5000)
        self.recognizer = cv2.FaceRecognizerSF.create(str(settings.recognizer_model), "")

    # ---- decoding -----------------------------------------------------------------
    def decode(self, contents: bytes) -> np.ndarray:
        if len(contents) > self.settings.max_upload_bytes:
            raise FaceError("Image exceeds the upload size limit")
        if not contents.startswith((JPEG_MAGIC, PNG_MAGIC)):
            raise FaceError("Upload a JPEG or PNG image")
        frame = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise FaceError("The image could not be decoded")
        h, w = frame.shape[:2]
        if h * w > self.settings.max_upload_pixels:
            raise FaceError("Image resolution is too large; resize it first")
        if max(h, w) > 1280:
            scale = 1280 / max(h, w)
            frame = cv2.resize(frame, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
        return frame

    # ---- detection + embedding -----------------------------------------------------
    def detect(self, frame: np.ndarray) -> list[DetectedFace]:
        h, w = frame.shape[:2]
        with self._lock:
            self.detector.setInputSize((w, h))
            _, faces = self.detector.detect(frame)
            if faces is None:
                return []
            results = []
            for row in faces:
                x, y, fw, fh = (int(round(v)) for v in row[:4])
                if min(fw, fh) < self.settings.min_face_size:
                    continue
                aligned = self.recognizer.alignCrop(frame, row)
                embedding = self.recognizer.feature(aligned).flatten().astype(np.float32)
                embedding /= np.linalg.norm(embedding) or 1.0
                results.append(DetectedFace((max(0, x), max(0, y), fw, fh), float(row[-1]), embedding))
        # Largest face first: the visitor standing at the door, not someone in the background.
        return sorted(results, key=lambda f: f.box[2] * f.box[3], reverse=True)

    def primary_face(self, frame: np.ndarray) -> DetectedFace:
        faces = self.detect(frame)
        if not faces:
            raise FaceError("No clear front-facing face was found in the photo")
        return faces[0]

    # ---- matching --------------------------------------------------------------------
    def match(self, embedding: np.ndarray, references: list[dict]) -> Match:
        """references: [{person_id, name, role, embedding: np.ndarray}]"""
        best: dict | None = None
        best_score = -1.0
        for ref in references:
            score = float(np.dot(embedding, ref["embedding"]))
            if score > best_score:
                best, best_score = ref, score
        if best is not None and best_score >= self.settings.match_threshold:
            return Match(best["person_id"], best["name"], best["role"], round(best_score, 3), True)
        return Match(None, "Unknown", "unknown", round(max(best_score, 0.0), 3), False)

    @staticmethod
    def annotate(frame: np.ndarray, face: DetectedFace | None, match: Match | None) -> np.ndarray:
        canvas = frame.copy()
        if face is None or match is None:
            return canvas
        x, y, w, h = face.box
        color = {"owner": (90, 210, 80), "relative": (40, 180, 240)}.get(match.role, (60, 60, 235))
        label = (f"{match.name} [{match.role}] {match.score:.2f}" if match.authorized
                 else f"UNKNOWN {match.score:.2f}")
        cv2.rectangle(canvas, (x, y), (x + w, y + h), color, 2)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        top = max(th + 8, y)
        cv2.rectangle(canvas, (x, top - th - 8), (x + tw + 8, top), color, -1)
        cv2.putText(canvas, label, (x + 4, top - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (15, 15, 15), 1, cv2.LINE_AA)
        return canvas

    @staticmethod
    def encode_jpeg(frame: np.ndarray, quality: int = 88) -> bytes:
        ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            raise FaceError("Could not encode image")
        return buffer.tobytes()
