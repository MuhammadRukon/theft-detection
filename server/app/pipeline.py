import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import numpy as np

from app.behavior import Alert, BehaviorEngine
from app.detection.base import Detector
from app.events import DetectionsEvent, EventBus, Track
from app.metrics import RollingStats
from app.sources import Frame, FrameSource
from app.sources.fps import RollingFps
from app.tracking import PersonTracker, TrackedDetection

log = logging.getLogger(__name__)
_log_clock = time.monotonic  # the throttle's own clock, so tests can fake it alone


class _ErrorLogThrottle:
    """Rate-limits repeated failure tracebacks to one per `interval` seconds, counting the rest.

    One instance per call site: a failing detector must not silence the behavior engine.
    """

    def __init__(self, interval: float = 30.0):
        self._interval = interval
        self._last: float | None = None
        self._suppressed = 0

    def log(self, logger: logging.Logger, msg: str, *args: object) -> None:
        now = _log_clock()
        if self._last is None or now - self._last >= self._interval:
            # First failure of a streak, or the window elapsed: report with the count suppressed.
            if self._last is not None:
                msg = f"{msg} ({self._suppressed} suppressed since last log)"
            logger.exception(msg, *args)
            self._last = now
            self._suppressed = 0
        else:
            self._suppressed += 1


@dataclass(frozen=True)
class PipelineStats:
    # Metrics are None until the first inference. e2e_latency_ms is the mean of the last 30
    # results, decode-to-publish (source frame.ts to bus.publish), not camera-to-browser.
    inference_fps: float | None = None
    inference_ms_p50: float | None = None
    inference_ms_p95: float | None = None
    e2e_latency_ms: float | None = None
    status: Literal["loading", "running", "failed"] = "loading"


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
        on_alert: Callable[[Alert], None] | None = None,
        engine: BehaviorEngine | None = None,
        alert_sink: Callable[[Alert, np.ndarray, list[TrackedDetection]], object] | None = None,
    ):
        self._source = source
        self._detector = detector
        self._tracker = tracker
        self._bus = bus
        self._camera_id = camera_id
        self._period = 1 / fps
        # Alert seam: process() runs the engine after the tracker and calls this per alert;
        # eval.py collects them here.
        self._on_alert = on_alert
        self._alert_sink = alert_sink  # (alert, image, tracked): the live app's AlertService.handle
        self._engine = engine
        self.engine_errors = 0  # swallowed in process(); tools/eval.py fails a clip on any
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._fps = RollingFps()
        self._lock = threading.Lock()
        self._infer_ms = RollingStats(30)
        self._e2e_ms = RollingStats(30)
        self._status: Literal["loading", "running", "failed"] = "loading"
        self._inference_error_log = _ErrorLogThrottle()
        self._engine_error_log = _ErrorLogThrottle()

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
            return PipelineStats(status=self._status)
        return PipelineStats(
            round(self._fps.fps(), 2), round(p50, 2), round(p95, 2), round(e2e, 2), self._status
        )

    def _run(self) -> None:
        try:
            detector = self._detector if isinstance(self._detector, Detector) else self._detector()
        except Exception:
            log.exception("%s: detector failed to load, detection disabled", self._camera_id)
            self._status = "failed"
            return
        self._status = "running"
        last = None
        while not self._stop.is_set():
            frame = self._source.latest()
            if frame is None or frame is last:
                self._stop.wait(0.01)
                continue
            last = frame
            t0 = time.monotonic()
            try:
                self.process(detector, frame)
            except Exception:
                self._inference_error_log.log(log, "%s: inference error", self._camera_id)
            # a slow detector overruns the period: the wait is 0 and the next newest frame is taken
            self._stop.wait(max(t0 + self._period - time.monotonic(), 0))

    def process(self, detector: Detector, frame: Frame) -> None:
        """Detect, track and publish one frame. Shared by the live loop and tools/eval.py."""
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
        if self._engine:
            try:  # a rule or alert-handler bug must never stop detections being published
                for alert in self._engine.update(tracked, w, h, frame.src_ts, frame.ts):
                    if self._on_alert:
                        self._on_alert(alert)
                    if self._alert_sink:
                        self._alert_sink(alert, frame.image, tracked)
            except Exception:
                self.engine_errors += 1
                self._engine_error_log.log(log, "%s: behavior engine error", self._camera_id)
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
