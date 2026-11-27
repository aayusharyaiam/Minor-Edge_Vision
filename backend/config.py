"""Validated configuration. Paths are anchored to the project, not the shell CWD."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    server_host: str = "127.0.0.1"
    server_port: int = Field(default=8000, ge=1, le=65535)

    # Recognition (YuNet detector + SFace embeddings, cosine similarity).
    match_threshold: float = Field(default=0.40, gt=0, lt=1)
    detection_score: float = Field(default=0.80, gt=0, lt=1)
    min_face_size: int = Field(default=60, ge=20)
    max_frames: int = Field(default=6, ge=1, le=10)

    # Mock hardware / decision timings.
    relay_seconds: float = Field(default=10.0, gt=0)
    approval_seconds: float = Field(default=90.0, gt=0)
    pir_hold_seconds: float = Field(default=2.0, gt=0)

    admin_api_key: str = ""
    max_upload_bytes: int = Field(default=8 * 1024 * 1024, ge=1024)
    max_upload_pixels: int = Field(default=16_000_000, ge=10_000)

    models_dir: Path = BASE_DIR / "models"
    authorized_dir: Path = BASE_DIR / "authorized_faces"
    snapshots_dir: Path = BASE_DIR / "snapshots"
    database_path: Path = BASE_DIR / "data" / "edgevision.sqlite3"
    frontend_dist: Path = BASE_DIR / "frontend" / "dist"

    @property
    def detector_model(self) -> Path:
        return self.models_dir / "face_detection_yunet_2023mar.onnx"

    @property
    def recognizer_model(self) -> Path:
        return self.models_dir / "face_recognition_sface_2021dec.onnx"

    def prepare_directories(self) -> None:
        for path in (self.authorized_dir, self.snapshots_dir, self.database_path.parent):
            path.mkdir(parents=True, exist_ok=True)
