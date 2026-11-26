import asyncio
from collections.abc import Iterator
from contextlib import contextmanager

from pydantic import BaseModel


class EventBus:
    """Worker threads publish; SSE tasks subscribe. Slow subscribers lose their oldest events,
    taking those without a truthy `keep` attribute first."""

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
            if not q.full():
                q.put_nowait(event)
                continue
            items = [q.get_nowait() for _ in range(q.qsize())] + [event]
            drop = next((i for i, e in enumerate(items) if not getattr(e, "keep", False)), 0)
            del items[drop]
            for item in items:
                q.put_nowait(item)

    @contextmanager
    def subscribe(self) -> Iterator[asyncio.Queue[BaseModel]]:
        q: asyncio.Queue[BaseModel] = asyncio.Queue(self._maxsize)
        self._subs.add(q)
        try:
            yield q
        finally:
            self._subs.discard(q)
