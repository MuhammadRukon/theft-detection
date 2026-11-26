import threading
import time

import numpy as np
import pytest

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
            self._frame = Frame(
                "cam1",
                time.time(),
                self.produced * self.interval,
                None,
                W,
                H,
                np.zeros((H, W, 3), np.uint8),
            )

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


class FlakyDetector(FakeDetector):
    """Raises on the frames where `fail` says so; by default on every frame."""

    def __init__(self, fail=lambda call: True):
        super().__init__([BOX])
        self.fail = fail

    def detect(self, image):
        found = super().detect(image)
        if self.fail(self.calls):
            raise RuntimeError("boom")
        return found


class FailingEngine:
    def update(self, *args):
        raise RuntimeError("rule bug")


class ScriptedSource:
    """One fresh frame per entry in `times`, setting the log clock to it, then stops the loop.

    Lets a test call Pipeline._run() on its own thread: no background threads, nothing to wait on.
    """

    def __init__(self):
        self.now, self.times, self.pipeline = 0.0, [], None

    def latest(self):
        if not self.times:
            self.pipeline._stop.set()
            return None
        self.now = self.times.pop(0)
        return Frame("cam1", time.time(), 0.0, None, W, H, np.zeros((H, W, 3), np.uint8))


@pytest.fixture
def scripted(monkeypatch, caplog):
    caplog.set_level("ERROR", logger="app.pipeline")
    src, bus = ScriptedSource(), Bus()
    # raising=False: without the hook the tests still reach their assertions and fail there
    monkeypatch.setattr("app.pipeline._log_clock", lambda: src.now, raising=False)

    def build(detector, engine=None):
        src.pipeline = Pipeline(
            src, detector, PersonTracker(1000), bus, "cam1", 1000, engine=engine
        )

        def run(*times):
            src.times = list(times)
            src.pipeline._stop.clear()
            src.pipeline._run()

        return src.pipeline, bus, run

    return build


def _traces(caplog, msg):
    return [r.getMessage() for r in caplog.records if msg in r.getMessage() and r.exc_info]


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


def test_detector_error_logs_once_per_window_and_counts_suppressed(scripted, caplog):
    _, bus, run = scripted(FlakyDetector())
    run(1000, 1000, 1000, 1000, 1029.9)
    assert len(_traces(caplog, "inference error")) == 1
    run(1030)
    traces = _traces(caplog, "inference error")
    assert len(traces) == 2 and "(4 suppressed since last log)" in traces[1]
    assert bus.events == []


def test_engine_error_logs_once_per_window_and_counts_suppressed(scripted, caplog):
    _, bus, run = scripted(FakeDetector([BOX]), FailingEngine())
    run(1000, 1000, 1000, 1029.9)
    assert len(_traces(caplog, "behavior engine error")) == 1
    run(1030)
    traces = _traces(caplog, "behavior engine error")
    assert len(traces) == 2 and "(3 suppressed since last log)" in traces[1]
    assert len(bus.events) == 5  # detections still published


def test_inference_and_engine_error_windows_are_independent(scripted, caplog):
    # odd calls fail in the detector, even calls get through to the failing engine
    _, _, run = scripted(FlakyDetector(lambda call: call % 2 == 1), FailingEngine())
    run(1000, 1000, 1000, 1000)
    assert len(_traces(caplog, "inference error")) == 1
    assert len(_traces(caplog, "behavior engine error")) == 1


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
    src._frame = Frame("cam1", time.time(), 0.0, None, W, H, np.zeros((H, W, 3), np.uint8))
    p.start()
    time.sleep(0.3)
    p.stop()
    src.close()
    assert det.calls == 1


def test_engine_alert_goes_through_on_alert_and_engine_errors_are_contained():
    from app.behavior import BehaviorEngine, DwellRule, Zone

    zone = Zone("z", ((0, 0), (1, 0), (1, 1), (0, 1)), 0.05)
    alerts = []
    src, bus, p = make(FakeDetector([BOX]), interval=0.01)
    p._engine = BehaviorEngine("cam1", [zone], [DwellRule()])
    p._on_alert = alerts.append
    p.start()
    assert wait_for(lambda: alerts)
    p.stop()
    src.close()
    a = alerts[0]
    assert a.type == "dwell" and a.zone == "z" and a.camera_id == "cam1" and a.score == 60
    assert any(e.tracks for e in bus.events)

    def boom(alert):
        raise RuntimeError("handler bug")

    src, bus, p = make(FakeDetector([BOX]))
    p._engine = BehaviorEngine("cam1", [zone], [DwellRule(cooldown_s=0)])
    p._on_alert = boom
    p.start()
    assert wait_for(lambda: len(bus.events) >= 10)  # detections keep flowing
    p.stop()
    src.close()
