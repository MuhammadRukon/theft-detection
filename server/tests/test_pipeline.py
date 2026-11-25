import threading
import time

import numpy as np

from app.detection.base import Detection, FakeDetector
from app.events import DetectionsEvent
from app.pipeline import Pipeline
from app.sources.base import Frame
from app.tracking import PersonTracker

W, H = 200, 100
BOX = Detection(0, "person", 0.9, 20, 10, 100, 60)


class StubSource:
    """Produces a fresh frame every `interval` seconds on its own thread, like a camera."""

    def __init__(self, interval=0.01):
        self.interval, self.produced = interval, 0
        self._frame = None
        self._stop = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while not self._stop.wait(self.interval):
            self.produced += 1
            self._frame = Frame("cam1", time.time(), None, W, H, np.zeros((H, W, 3), np.uint8))

    def latest(self):
        return self._frame

    def close(self):
        self._stop.set()


class Bus:
    def __init__(self):
        self.events = []

    def publish(self, e):
        self.events.append(e)


def make(detector, fps=50.0, interval=0.01):
    src, bus = StubSource(interval), Bus()
    return src, bus, Pipeline(src, detector, PersonTracker(fps), bus, "cam1", fps)


def wait_for(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while not cond() and time.monotonic() < end:
        time.sleep(0.01)
    return cond()


def test_publishes_normalized_tracks_after_confirmation():
    src, bus, p = make(FakeDetector([BOX]))
    p.start()
    assert wait_for(lambda: any(e.tracks for e in bus.events))
    p.stop()
    src.close()
    assert not bus.events[0].tracks  # first sighting is unconfirmed: empty event, still published
    e = next(e for e in bus.events if e.tracks)
    assert isinstance(e, DetectionsEvent) and e.camera_id == "cam1" and e.latency_ms >= 0
    t = e.tracks[0]
    assert (t.x1, t.y1, t.x2, t.y2) == (0.1, 0.1, 0.5, 0.6) and t.class_name == "person"


def test_empty_detections_still_published_and_clamped():
    src, bus, p = make(FakeDetector())
    p.start()
    assert wait_for(lambda: len(bus.events) >= 2)
    p.stop()
    src.close()
    assert all(e.tracks == [] for e in bus.events)

    big = Detection(0, "person", 0.9, -10, -10, 1000, 1000)
    src, bus, p = make(FakeDetector([big]))
    p.start()
    assert wait_for(lambda: any(e.tracks for e in bus.events))
    p.stop()
    src.close()
    t = next(e for e in bus.events if e.tracks).tracks[0]
    assert (t.x1, t.y1, t.x2, t.y2) == (0, 0, 1, 1)


def test_slow_detector_sees_only_newest_frames():
    det = FakeDetector(delay_s=0.3)
    src, bus, p = make(det)
    p.start()
    time.sleep(1.5)
    produced = src.produced
    p.stop()
    src.close()
    assert 2 <= det.calls <= 6 and produced > 5 * det.calls


def test_rate_limited_to_fps():
    det = FakeDetector()
    src, bus, p = make(det, fps=10.0, interval=0.005)
    p.start()
    time.sleep(1.0)
    p.stop()
    src.close()
    assert 5 <= det.calls <= 13


def test_detector_exception_does_not_kill_loop():
    class Flaky(FakeDetector):
        def detect(self, image):
            super().detect(image)
            if self.calls == 1:
                raise RuntimeError("boom")
            return []

    src, bus, p = make(Flaky())
    p.start()
    assert wait_for(lambda: len(bus.events) >= 2)
    p.stop()
    src.close()


def test_failed_detector_load_is_contained():
    def boom():
        raise RuntimeError("no model")

    src, bus, p = make(boom)
    p.start()
    time.sleep(0.2)
    p.stop()
    src.close()
    assert bus.events == [] and p.stats().inference_fps is None


def test_stop_is_prompt():
    src, bus, p = make(FakeDetector(), fps=0.2)  # 5 s period
    p.start()
    assert wait_for(lambda: bus.events)
    t0 = time.monotonic()
    p.stop()
    src.close()
    assert time.monotonic() - t0 < 1.0


def test_stats_none_then_populated():
    src, bus, p = make(FakeDetector(delay_s=0.01))
    assert p.stats() == p.stats().__class__()
    assert p.stats().inference_ms_p50 is None
    p.start()
    assert wait_for(lambda: len(bus.events) >= 5)
    s = p.stats()
    p.stop()
    src.close()
    assert (
        s.inference_fps > 0
        and s.inference_ms_p50 >= 10
        and s.inference_ms_p95 >= s.inference_ms_p50
    )
    assert s.e2e_latency_ms >= 0


def test_status_transitions_and_failed_load():
    def boom():
        raise RuntimeError("no model")

    src, bus, p = make(boom)
    assert p.stats().status == "loading"
    p.start()
    assert wait_for(lambda: p.stats().status == "failed")
    p.stop()
    src.close()

    src, bus, p = make(FakeDetector())
    assert p.stats().status == "loading"
    p.start()
    assert wait_for(lambda: p.stats().status == "running")
    assert wait_for(lambda: p.stats().inference_fps is not None)
    assert p.stats().status == "running"
    p.stop()
    src.close()


def test_same_frame_not_reprocessed():
    det = FakeDetector()
    src, bus, p = make(det, interval=1000)  # StubSource never produces a frame
    src._frame = Frame("cam1", time.time(), None, W, H, np.zeros((H, W, 3), np.uint8))
    p.start()
    time.sleep(0.3)
    p.stop()
    src.close()
    assert det.calls == 1
