import threading
import time
from collections import deque


class RollingFps:
    """Frames per second over the last `window` seconds. Reads 0 once frames stop."""

    def __init__(self, window: float = 3.0, clock=time.monotonic):
        self._window = window
        self._clock = clock
        self._ticks: deque[float] = deque()
        self._lock = threading.Lock()

    def tick(self) -> None:
        with self._lock:
            self._ticks.append(self._clock())
            self._prune()

    def _prune(self) -> None:
        cutoff = self._clock() - self._window
        while self._ticks and self._ticks[0] < cutoff:
            self._ticks.popleft()

    def fps(self) -> float:
        with self._lock:
            self._prune()
            if len(self._ticks) < 2:
                return 0.0
            return (len(self._ticks) - 1) / (self._ticks[-1] - self._ticks[0])
