import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.detection.base import Detector
from app.events import DetectionsEvent, EventBus, Track
from app.metrics import RollingStats
from app.sources import Frame, FrameSource
from app.sources.fps import RollingFps
from app.tracking import PersonTracker

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineStats:
    # All None until the first inference. e2e_latency_ms is the mean of the last 100 results.
    inference_fps: float | None = None
    inference_ms_p50: float | None = None
    inference_ms_p95: float | None = None
    e2e_latency_ms: float | None = None


class Pipeline:
    """Newest frame -> detect -> track -> publish, at most `fps` times a second, on its own thread.

    `detector` may be a zero-arg factory; it is called on the pipeline thread so a slow model
    load never delays startup, and a failed load leaves ingest and SSE running.
    """

    def __init__(
        self,
        source: FrameSource,
        detector: Detector | Callable[[], Detector],
        tracker: PersonTracker,
        bus: EventBus,
        camera_id: str,
        fps: float,
    ):
        self._source = source
        self._detector = detector
        self._tracker = tracker
        self._bus = bus
        self._camera_id = camera_id
        self._period = 1 / fps
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._fps = RollingFps()
        self._lock = threading.Lock()
        self._infer_ms = RollingStats()
        self._e2e_ms = RollingStats()

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name=f"pipeline-{self._camera_id}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)

    def stats(self) -> PipelineStats:
        with self._lock:
            p50, p95, e2e = self._infer_ms.p50(), self._infer_ms.p95(), self._e2e_ms.mean()
        if p50 is None:
            return PipelineStats()
        return PipelineStats(round(self._fps.fps(), 2), round(p50, 2), round(p95, 2), round(e2e, 2))

    def _run(self) -> None:
        try:
            detector = self._detector if isinstance(self._detector, Detector) else self._detector()
        except Exception:
            log.exception("%s: detector failed to load, detection disabled", self._camera_id)
            return
        last_ts = None
        while not self._stop.is_set():
            frame = self._source.latest()
            if frame is None or frame.ts == last_ts:
                self._stop.wait(0.01)
                continue
            last_ts = frame.ts
            t0 = time.monotonic()
            try:
                self._process(detector, frame)
            except Exception:
                log.exception("%s: inference error", self._camera_id)
            # a slow detector overruns the period: the wait is 0 and the next newest frame is taken
            self._stop.wait(max(t0 + self._period - time.monotonic(), 0))

    def _process(self, detector: Detector, frame: Frame) -> None:
        t0 = time.perf_counter()
        detections = detector.detect(frame.image)
        infer_ms = (time.perf_counter() - t0) * 1000
        tracked = self._tracker.update(detections)
        w, h = frame.width, frame.height
        tracks = [
            Track(
                track_id=t.track_id,
                class_name=t.class_name,
                conf=t.conf,
                x1=min(max(t.x1 / w, 0), 1),
                y1=min(max(t.y1 / h, 0), 1),
                x2=min(max(t.x2 / w, 0), 1),
                y2=min(max(t.y2 / h, 0), 1),
            )
            for t in tracked
        ]
        latency_ms = (time.time() - frame.ts) * 1000
        # Published even when empty, so the overlay clears.
        self._bus.publish(
            DetectionsEvent(
                camera_id=self._camera_id,
                frame_ts=frame.ts,
                latency_ms=latency_ms,
                tracks=tracks,
            )
        )
        self._fps.tick()
        with self._lock:
            self._infer_ms.add(infer_ms)
            self._e2e_ms.add(latency_ms)
