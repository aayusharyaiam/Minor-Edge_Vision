"""Access rules. Recognition alone never drives the lock: identity, confidence
and per-role permissions decide together."""

from __future__ import annotations

from dataclasses import dataclass

from backend.face_engine import Match

GRANTED, PENDING, DENIED = "GRANTED", "PENDING", "DENIED"
REPEATED_ATTEMPTS = 3


@dataclass(frozen=True)
class Decision:
    decision: str  # GRANTED | PENDING | DENIED
    identity: str  # owner | relative | intruder
    reason: str
    repeated_attempts: bool = False


def decide(match: Match, threshold: float, failed_attempts: int = 0) -> Decision:
    if match.authorized and match.score >= threshold:
        if match.role == "owner":
            return Decision(GRANTED, "owner",
                            f"Owner {match.name} matched ({match.score:.2f} ≥ {threshold:.2f}); door unlocks")
        if match.role == "relative":
            return Decision(PENDING, "relative",
                            f"Relative {match.name} matched ({match.score:.2f}); waiting for owner approval")
    repeated = failed_attempts + 1 >= REPEATED_ATTEMPTS
    reason = f"No registered face matched (best {match.score:.2f} < {threshold:.2f}); door stays locked"
    if repeated:
        reason += f" — {failed_attempts + 1} failed attempts"
    return Decision(DENIED, "intruder", reason, repeated)
