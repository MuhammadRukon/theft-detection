import logging
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

import av
import numpy as np

from app.sources.fps import RollingFps

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Frame:
    camera_id: str
    ts: float  # wall clock at decode; used for latency only
    # Source (video) time in seconds, 0 at the first frame, monotonic per source (a looping file
    # keeps counting up). Rules use this, so a clip replays the same at any speed.
    src_ts: float
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
        # Called on the reader thread for every frame, none skipped (replay/eval); may block.
        self.on_frame: Callable[[Frame], None] | None = None
        # Set when a one-shot source (stop_on_end) has finished or failed; `error` says why.
        self.ended = threading.Event()
        self.error: Exception | None = None
        self._src_first: float | None = None
        self._src_offset = 0.0
        self._src_last: float | None = None
        self._src_mono = 0.0  # monotonic time of the last stamped frame
        self._src_has_pts = False

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
    # True: live source, so source time includes the outage between sessions. Files set False to
    # keep source time free of the wall clock.
    count_gaps = True
    # True: one-shot source. End of stream or any error sets `ended` and the reader stops.
    stop_on_end = False

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self._new_session()
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
                            self._publish(frame, image, share + (time.perf_counter() - t1) * 1000)
                            if self._pace(frame):
                                return
                    if self.loop_on_end:
                        continue
                    if self.stop_on_end:
                        self.ended.set()
                        return
                    log.warning("%s: stream ended", self.camera_id)
            except (av.FFmpegError, OSError) as e:
                if self._fail(e):
                    return
                log.warning("%s: unavailable (%s), retry in %.0fs", self.camera_id, e, backoff)
            except Exception as e:
                if self._fail(e):
                    return
                log.exception("%s: reader error, retry in %.0fs", self.camera_id, backoff)
            self._stop.wait(backoff)
            backoff = min(backoff * 2, 10.0)

    def _fail(self, e: Exception) -> bool:
        """One-shot sources record the error and stop; others retry."""
        if not self.stop_on_end:
            return False
        self.error = e
        log.error("%s: source failed (%s)", self.camera_id, e)
        self.ended.set()
        return True

    def _new_session(self) -> None:
        """Source time restarts at each (re)open; _source_ts continues after the last frame."""
        self._src_first = None

    def _source_ts(self, frame) -> float:
        # One clock per session, picked by its first frame: pts (frame.time is pts * time_base),
        # else monotonic time (some RTSP streams carry no pts).
        # shortcut: in a pts session a frame without pts repeats the last stamp, so a stream that
        # drops pts for good stalls source time until the next reconnect.
        mono = time.monotonic()
        first_of_session = self._src_first is None
        if first_of_session:
            self._src_has_pts = frame.pts is not None
        if not self._src_has_pts:
            t = mono
        else:
            t = frame.time if frame.pts is not None else None
        if first_of_session:
            gap = max(mono - self._src_mono, 0.001) if self.count_gaps else 0.001
            self._src_offset = 0.0 if self._src_last is None else self._src_last + gap
            self._src_first = t
        self._src_mono = mono
        if t is None:
            return self._src_last
        ts = self._src_offset + t - self._src_first
        if self._src_last is not None and ts < self._src_last:
            # timestamps jumped back: hold this frame and shift the base so time keeps advancing
            self._src_offset += self._src_last - ts
            ts = self._src_last
        self._src_last = ts
        return ts

    def _publish(self, av_frame, image: np.ndarray, decode_ms: float) -> None:
        h, w = image.shape[:2]
        frame = Frame(
            self.camera_id, time.time(), self._source_ts(av_frame), av_frame.pts, w, h, image
        )
        self._slot.put(frame)
        if self.on_frame:
            self.on_frame(frame)
        self._fps.tick()
        with self._lock:
            self._total += 1
            self._decode_ms_sum += decode_ms
            self._size = (w, h)
