import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

from app.sources.fps import RollingFps


@dataclass(frozen=True)
class Frame:
    camera_id: str
    ts: float  # wall clock at decode
    pts: int | None
    width: int
    height: int
    image: np.ndarray  # bgr24


class LatestSlot:
    """One-slot buffer: a new frame replaces an unread one and counts a drop."""

    def __init__(self):
        self._frame: Frame | None = None
        self._unread = False
        self.dropped = 0
        self._lock = threading.Lock()

    def put(self, frame: Frame) -> None:
        with self._lock:
            if self._unread:
                self.dropped += 1
            self._frame, self._unread = frame, True

    def get(self) -> Frame | None:
        with self._lock:
            self._unread = False
            return self._frame


class FrameSource(ABC):
    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self._slot = LatestSlot()
        self._fps = RollingFps()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._total = 0
        self._decode_ms_sum = 0.0
        self._size: tuple[int, int] | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name=f"source-{self.camera_id}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)

    def latest(self) -> Frame | None:
        return self._slot.get()

    def stats(self) -> dict:
        with self._lock:
            total, ms_sum, size = self._total, self._decode_ms_sum, self._size
        return {
            "camera_id": self.camera_id,
            "fps": round(self._fps.fps(), 2),
            "width": size[0] if size else None,
            "height": size[1] if size else None,
            "decode_ms": round(ms_sum / total, 2) if total else None,
            "frames_total": total,
            "frames_dropped": self._slot.dropped,
        }

    def _emit(self, frame, decode_ms: float) -> None:
        """Convert a PyAV frame to bgr24, publish it to the slot, update stats."""
        t0 = time.perf_counter()
        image = frame.to_ndarray(format="bgr24")
        decode_ms += (time.perf_counter() - t0) * 1000
        h, w = image.shape[:2]
        self._slot.put(Frame(self.camera_id, time.time(), frame.pts, w, h, image))
        self._fps.tick()
        with self._lock:
            self._total += 1
            self._decode_ms_sum += decode_ms
            self._size = (w, h)

    @abstractmethod
    def _run(self) -> None: ...
