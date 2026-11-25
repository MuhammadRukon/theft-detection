import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import av
import numpy as np

from app.sources.fps import RollingFps

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Frame:
    camera_id: str
    ts: float  # wall clock at decode
    pts: int | None
    width: int
    height: int
    image: np.ndarray  # bgr24


@dataclass(frozen=True)
class SourceStats:
    camera_id: str
    fps: float
    width: int | None
    height: int | None
    decode_ms: float | None
    frames_total: int
    # frames overwritten before the consumer read them: ~ingest fps minus inference fps per second
    # (15 fps ingest, 5 fps consumer: about 10/s)
    frames_dropped: int


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

    def stats(self) -> SourceStats:
        with self._lock:
            total, ms_sum, size = self._total, self._decode_ms_sum, self._size
        return SourceStats(
            camera_id=self.camera_id,
            fps=round(self._fps.fps(), 2),
            width=size[0] if size else None,
            height=size[1] if size else None,
            decode_ms=round(ms_sum / total, 2) if total else None,
            frames_total=total,
            frames_dropped=self._slot.dropped,
        )

    @abstractmethod
    def _open(self):
        """Return an opened av container (a context manager)."""

    def _pace(self, frame) -> bool:
        """Per-frame hook; return True to stop the source."""
        return False

    # True: a clean end of stream (e.g. file EOF) reopens at once instead of backing off.
    loop_on_end = False

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                with self._open() as container:
                    backoff = 1.0
                    for packet in container.demux(video=0):
                        if self._stop.is_set():
                            return
                        # decode_ms per frame = its share of the packet decode + bgr24 conversion.
                        t0 = time.perf_counter()
                        frames = packet.decode()
                        share = (time.perf_counter() - t0) * 1000 / max(len(frames), 1)
                        for frame in frames:
                            t1 = time.perf_counter()
                            image = frame.to_ndarray(format="bgr24")
                            self._publish(
                                frame.pts, image, share + (time.perf_counter() - t1) * 1000
                            )
                            if self._pace(frame):
                                return
                    if self.loop_on_end:
                        continue
                    log.warning("%s: stream ended", self.camera_id)
            except (av.FFmpegError, OSError) as e:
                log.warning("%s: unavailable (%s), retry in %.0fs", self.camera_id, e, backoff)
            except Exception:
                log.exception("%s: reader error, retry in %.0fs", self.camera_id, backoff)
            self._stop.wait(backoff)
            backoff = min(backoff * 2, 10.0)

    def _publish(self, pts, image: np.ndarray, decode_ms: float) -> None:
        h, w = image.shape[:2]
        self._slot.put(Frame(self.camera_id, time.time(), pts, w, h, image))
        self._fps.tick()
        with self._lock:
            self._total += 1
            self._decode_ms_sum += decode_ms
            self._size = (w, h)
