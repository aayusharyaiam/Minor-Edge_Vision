"""Software stand-ins for the ESP32-CAM's PIR sensor and door relay/servo.

The door relocks itself from a watchdog thread, like the firmware timer will.
Swap MockRelayDriver for a serial/HTTP driver when the real ESP32 is wired up.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Protocol

log = logging.getLogger(__name__)


class RelayDriver(Protocol):
    def set_unlocked(self, unlocked: bool, duration: float = 0) -> None: ...


class MockRelayDriver:
    def set_unlocked(self, unlocked: bool, duration: float = 0) -> None:
        if unlocked:
            log.info("[RELAY IO14] HIGH -> door unlocked for %gs", duration)
        else:
            log.info("[RELAY IO14] LOW -> door locked")


class MockPIR:
    def __init__(self, hold_seconds: float):
        self.hold_seconds = hold_seconds
        self.high_until = 0.0
        self.triggers = 0

    def trigger(self) -> None:
        self.high_until = time.monotonic() + self.hold_seconds
        self.triggers += 1
        log.info("[PIR IO13] HIGH -> motion detected")

    def active(self) -> bool:
        return time.monotonic() < self.high_until


class Door:
    def __init__(self, driver: RelayDriver, open_seconds: float,
                 on_change: Callable[[dict], None] = lambda status: None):
        self.driver, self.open_seconds, self.on_change = driver, open_seconds, on_change
        self.unlocked = False
        self.unlock_until = 0.0
        self.opened_by: str | None = None
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._watch, name="door-watchdog", daemon=True)

    def start(self) -> None:
        self.lock()
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2)
        self.lock()

    def unlock(self, opened_by: str) -> None:
        with self._lock:
            self.driver.set_unlocked(True, self.open_seconds)
            self.unlocked, self.opened_by = True, opened_by
            self.unlock_until = time.monotonic() + self.open_seconds
        self.on_change(self.status())

    def lock(self) -> None:
        with self._lock:
            self.driver.set_unlocked(False)
            changed = self.unlocked
            self.unlocked, self.unlock_until, self.opened_by = False, 0.0, None
        if changed:
            self.on_change(self.status())

    def status(self) -> dict:
        with self._lock:
            return {"state": "UNLOCKED" if self.unlocked else "LOCKED",
                    "unlocked": self.unlocked, "opened_by": self.opened_by,
                    "seconds_remaining": round(max(0.0, self.unlock_until - time.monotonic()), 1)}

    def _watch(self) -> None:
        while not self._stop.wait(0.1):
            with self._lock:
                due = self.unlocked and time.monotonic() >= self.unlock_until
            if due:
                self.lock()
