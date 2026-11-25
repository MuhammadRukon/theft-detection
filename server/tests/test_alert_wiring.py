import asyncio

import cv2
import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.alerts import AlertService, AlertStore
from app.api.events import router
from app.behavior import Zone, make_engine
from app.detection.base import Detection, FakeDetector
from app.events import AlertEvent, DetectionsEvent, EventBus
from app.pipeline import Pipeline
from app.sources.file import FileFrameSource
from app.tracking import PersonTracker
from tests.test_eval import FPS, make_clip

ZONE = Zone("door", ((0, 0), (1, 0), (1, 1), (0, 1)), dwell_s=1.0)
PERSON = Detection(0, "person", 0.9, 20, 10, 40, 40)


def replay(tmp_path, service):
    """Run a 3 s clip through a real pipeline; returns the pipeline-side bus events."""
    make_clip(tmp_path / "c.mp4", seconds=3)
    bus = service.bus if service else EventBus()
    source = FileFrameSource("cam1", str(tmp_path / "c.mp4"), loop=False, realtime=False)
    detector = FakeDetector([PERSON])
    pipeline = Pipeline(
        source,
        detector,
        PersonTracker(FPS),
        bus,
        "cam1",
        FPS,
        engine=make_engine("cam1", [ZONE]),
        alert_sink=service.handle if service else None,
    )
    source.on_frame = lambda f: pipeline.process(detector, f)
    source.start()
    source.ended.wait()
    source.stop()
    assert source.error is None
    return detector.calls


def test_alert_reaches_store_bus_and_api(tmp_path):
    bus = EventBus(maxsize=1000)
    store = AlertStore(tmp_path / "alerts", 7)
    service = AlertService(store, bus, {"cam1": [ZONE]})

    async def go():
        bus.bind(asyncio.get_running_loop())
        with bus.subscribe() as q:
            await asyncio.to_thread(replay, tmp_path, service)
            await asyncio.sleep(0.1)
            return [q.get_nowait() for _ in range(q.qsize())]

    events = asyncio.run(go())
    alerts = [e for e in events if isinstance(e, AlertEvent)]
    assert len(alerts) == 1 and any(isinstance(e, DetectionsEvent) for e in events)
    (stored,) = store.list()
    assert stored == alerts[0] and stored.zone == "door"
    folder = tmp_path / "alerts" / stored.alert_id
    assert (folder / "alert.json").exists()
    assert cv2.imdecode(np.fromfile(folder / "snapshot.jpg", np.uint8), 1) is not None

    app = FastAPI()
    app.include_router(router)
    app.state.alert_store = store
    c = TestClient(app)
    assert [a["alert_id"] for a in c.get("/api/alerts").json()] == [stored.alert_id]
    r = c.get(stored.evidence_url)
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert cv2.imdecode(np.frombuffer(r.content, np.uint8), 1) is not None


def test_failing_store_does_not_stop_frames(tmp_path):
    class Broken(AlertStore):
        def save(self, event, jpeg):
            raise OSError("disk full")

    service = AlertService(Broken(tmp_path / "alerts", 7), EventBus(), {"cam1": [ZONE]})
    assert replay(tmp_path, service) == FPS * 3
    assert service.store.list() == []
