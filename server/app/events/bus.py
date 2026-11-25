import asyncio
from collections.abc import Iterator
from contextlib import contextmanager

from pydantic import BaseModel


class EventBus:
    """Worker threads publish; SSE tasks subscribe. Slow subscribers lose their oldest events."""

    def __init__(self, maxsize: int = 32):
        self._maxsize = maxsize
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subs: set[asyncio.Queue[BaseModel]] = set()

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish(self, event: BaseModel) -> None:
        """Thread-safe and non-blocking. No-op before bind() or after the loop is closed."""
        if self._loop is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._deliver, event)
        except RuntimeError:  # loop closed during shutdown
            pass

    def _deliver(self, event: BaseModel) -> None:
        for q in self._subs:
            if q.full():
                q.get_nowait()
            q.put_nowait(event)

    @contextmanager
    def subscribe(self) -> Iterator[asyncio.Queue[BaseModel]]:
        q: asyncio.Queue[BaseModel] = asyncio.Queue(self._maxsize)
        self._subs.add(q)
        try:
            yield q
        finally:
            self._subs.discard(q)
