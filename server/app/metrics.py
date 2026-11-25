from collections import deque


class RollingStats:
    """Bounded window of samples. Not thread-safe: the caller holds a lock."""

    def __init__(self, window: int = 100):
        self._values: deque[float] = deque(maxlen=window)

    def add(self, value: float) -> None:
        self._values.append(value)

    def _percentile(self, p: float) -> float | None:
        if not self._values:
            return None
        # nearest rank: the ceil(p/100 * n)-th smallest value
        ordered = sorted(self._values)
        return ordered[-(-len(ordered) * p // 100) - 1]

    def p50(self) -> float | None:
        return self._percentile(50)

    def p95(self) -> float | None:
        return self._percentile(95)

    def mean(self) -> float | None:
        return sum(self._values) / len(self._values) if self._values else None
