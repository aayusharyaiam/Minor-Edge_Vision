from backend.decision import DENIED, GRANTED, PENDING, decide
from backend.face_engine import FaceEngine, FaceError, Match

import pytest


def test_same_person_matches_and_stranger_does_not(settings, hopper_jpg, hopper_flipped_jpg, astronaut_jpg):
    engine = FaceEngine(settings)
    reference = engine.primary_face(engine.decode(hopper_jpg)).embedding
    refs = [{"person_id": "p1", "name": "Grace", "role": "owner", "embedding": reference}]
    same = engine.match(engine.primary_face(engine.decode(hopper_flipped_jpg)).embedding, refs)
    other = engine.match(engine.primary_face(engine.decode(astronaut_jpg)).embedding, refs)
    assert same.authorized and same.name == "Grace" and same.score > 0.8
    assert not other.authorized and other.role == "unknown"


def test_rejects_non_images_and_faceless_photos(settings, blank_jpg):
    engine = FaceEngine(settings)
    with pytest.raises(FaceError):
        engine.decode(b"not an image")
    with pytest.raises(FaceError):
        engine.primary_face(engine.decode(blank_jpg))


@pytest.mark.parametrize("role,score,expected,identity", [
    ("owner", 0.9, GRANTED, "owner"),
    ("relative", 0.9, PENDING, "relative"),
    ("unknown", 0.2, DENIED, "intruder"),
])
def test_decision_rules(role, score, expected, identity):
    match = Match("p" if role != "unknown" else None, "X", role, score, role != "unknown")
    result = decide(match, 0.4)
    assert (result.decision, result.identity) == (expected, identity)


def test_repeated_failures_are_flagged():
    assert decide(Match(None, "Unknown", "unknown", 0.1, False), 0.4, failed_attempts=2).repeated_attempts
