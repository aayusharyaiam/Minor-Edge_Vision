"""Fan-out of live events to WebSocket subscribers. publish() is thread-safe."""

from __future__ import annotations

import asyncio


class EventHub:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.subscribers: set[asyncio.Queue] = set()
        self.closed = False

    def publish(self, event: dict) -> None:
        if not self.closed and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self._deliver, event)

    def _deliver(self, event: dict) -> None:
        for subscriber in tuple(self.subscribers):
            if subscriber.full():
                subscriber.get_nowait()  # drop the oldest; clients resync over REST
            subscriber.put_nowait(event)

    def subscribe(self) -> asyncio.Queue:
        subscriber: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: asyncio.Queue) -> None:
        self.subscribers.discard(subscriber)

    def close(self) -> None:
        self.closed = True
        self.subscribers.clear()
