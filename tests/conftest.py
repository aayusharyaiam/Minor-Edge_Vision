from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def settings(tmp_path):
    configuration = Settings(
        _env_file=None, admin_api_key="", approval_seconds=90, relay_seconds=5,
        authorized_dir=tmp_path / "authorized_faces", snapshots_dir=tmp_path / "snapshots",
        database_path=tmp_path / "db.sqlite3",
        frontend_dist=tmp_path / "no-dist",
    )
    configuration.prepare_directories()
    return configuration


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def jpeg(path: Path, flip: bool = False) -> bytes:
    frame = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    if flip:
        frame = cv2.flip(frame, 1)
    return cv2.imencode(".jpg", frame)[1].tobytes()


@pytest.fixture
def hopper_jpg():
    return jpeg(FIXTURES / "grace_hopper.jpg")


@pytest.fixture
def hopper_flipped_jpg():
    return jpeg(FIXTURES / "grace_hopper.jpg", flip=True)


@pytest.fixture
def astronaut_jpg():
    return jpeg(FIXTURES / "astronaut.png")


@pytest.fixture
def blank_jpg():
    return cv2.imencode(".jpg", np.full((480, 640, 3), 128, np.uint8))[1].tobytes()
