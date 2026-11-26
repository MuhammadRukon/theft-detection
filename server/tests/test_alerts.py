import asyncio
import json
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.alerts import AlertService, AlertStore, render_snapshot, valid_alert_id
from app.api.events import events, router
from app.events import AlertEvent, EventBus, format_sse
from app.sources.base import SourceStats

JPEG = cv2.imencode(".jpg", np.zeros((8, 8, 3), np.uint8))[1].tobytes()


def mk(alert_id, ts=1000.0, camera_id="cam1", zone="door"):
    return AlertEvent(
        alert_id=alert_id, camera_id=camera_id, type="dwell", score=60, reason="r", zone=zone,
        track_ids=[1], src_ts=1.0, ts=ts, evidence_url=f"/api/alerts/{alert_id}/snapshot.jpg",
    )  # fmt: skip


def fake_alert(**kw):
    d = dict(type="dwell", zone="door", camera_id="cam1", src_ts=3.0, ts=1000.0,
             track_ids=(4,), reason="why", score=70)  # fmt: skip
    return SimpleNamespace(**{**d, **kw})


def test_store_roundtrip_order_reload(tmp_path):
    s = AlertStore(tmp_path, 7)
    for i in ("a1", "a3", "a2"):
        s.save(mk(i), JPEG)
    assert [a.alert_id for a in s.list(10)] == ["a3", "a2", "a1"]
    assert [a.alert_id for a in s.list(2)] == ["a3", "a2"]
    assert s.get("a1").reason == "r" and s.get("zz") is None
    assert s.snapshot_path("a1").read_bytes() == JPEG
    assert s.snapshot_path("zz") is None
    assert [a.alert_id for a in AlertStore(tmp_path, 7).list(10)] == ["a3", "a2", "a1"]


def test_null_zone_roundtrips_store_rest_and_sse(tmp_path):
    s = AlertStore(tmp_path, 7)
    s.save(mk("a1"), JPEG)
    s.save(mk("a2", zone=None), JPEG)
    reloaded = AlertStore(tmp_path, 7)
    assert [a.zone for a in reloaded.list()] == [None, "door"]
    assert [a["zone"] for a in client(reloaded).get("/api/alerts").json()] == [None, "door"]
    assert json.loads(format_sse("alert", reloaded.get("a2")).split("data: ")[1])["zone"] is None


def test_store_ignores_partial_and_corrupt(tmp_path):
    AlertStore(tmp_path, 7).save(mk("a1"), JPEG)
    (tmp_path / "a2").mkdir()
    (tmp_path / "a2" / "alert.json").write_text(mk("a2").model_dump_json())  # no snapshot
    (tmp_path / "a3").mkdir()
    (tmp_path / "a3" / "snapshot.jpg").write_bytes(JPEG)
    (tmp_path / "a3" / "alert.json").write_text("{not json")
    (tmp_path / ".tmp-x").mkdir()
    assert [a.alert_id for a in AlertStore(tmp_path, 7).list(10)] == ["a1"]


def test_store_save_failure_leaves_no_folder(tmp_path):
    s = AlertStore(tmp_path, 7)
    s.save(mk("a1"), JPEG)
    with pytest.raises(OSError):
        s.save(mk("a1"), JPEG)  # target exists, rename fails
    assert [p.name for p in tmp_path.iterdir()] == ["a1"]


def test_purge_expired(tmp_path):
    s = AlertStore(tmp_path, 1)
    s.save(mk("a1", ts=0), JPEG)
    s.save(mk("a2", ts=100_000), JPEG)
    assert s.purge_expired(now=100_000 + 10) == 1
    assert [a.alert_id for a in s.list(10)] == ["a2"]
    assert not (tmp_path / "a1").exists()


@pytest.mark.parametrize("bad", ["../x", "..\\x", "", "a" * 33, "A1", "a/b", "g1"])
def test_id_validation_rejects(bad):
    assert not valid_alert_id(bad)


def test_id_validation_accepts():
    assert valid_alert_id("0190abc12345def")


def test_render_snapshot():
    img = np.full((120, 160, 3), 128, np.uint8)
    tracks = [SimpleNamespace(track_id=4, x1=20, y1=20, x2=80, y2=100)]
    zones = [SimpleNamespace(name="door", polygon=[[0.5, 0.1], [0.9, 0.1], [0.9, 0.9]]),
             SimpleNamespace(name="other", polygon=[[0, 0], [0.2, 0], [0.2, 0.2]])]  # fmt: skip
    jpeg = render_snapshot(img, tracks, zones, fake_alert())
    out = cv2.imdecode(np.frombuffer(jpeg, np.uint8), 1)
    assert out.shape == img.shape
    assert np.abs(out.astype(int) - img).max() > 50
    assert (img == 128).all()  # input untouched


def test_render_snapshot_without_zone_highlights_none():
    img = np.full((120, 160, 3), 128, np.uint8)
    zones = [SimpleNamespace(name="door", polygon=[[0.5, 0.1], [0.9, 0.1], [0.9, 0.9]])]
    jpeg = render_snapshot(img, [], zones, fake_alert(zone=None))
    out = cv2.imdecode(np.frombuffer(jpeg, np.uint8), 1)
    inside = out[40, 130].astype(int)  # well inside the triangle: not filled
    assert np.abs(inside - 128).max() < 10


def test_service_keeps_null_zone(tmp_path):
    svc = AlertService(AlertStore(tmp_path, 7), EventBus(), {})
    ev = svc.handle(fake_alert(zone=None), np.zeros((20, 20, 3), np.uint8), [])
    assert ev is not None and ev.zone is None


def test_service_publishes_and_survives_failure(tmp_path):
    bus, store = EventBus(), AlertStore(tmp_path, 7)
    svc = AlertService(store, bus, {"cam1": []})
    img = np.zeros((20, 20, 3), np.uint8)

    async def go():
        bus.bind(asyncio.get_running_loop())
        with bus.subscribe() as q:
            ev = svc.handle(fake_alert(), img, [])
            got = await asyncio.wait_for(q.get(), 1)
            assert got == ev and ev.track_ids == [4] and valid_alert_id(ev.alert_id)
            assert ev.evidence_url == f"/api/alerts/{ev.alert_id}/snapshot.jpg"
            assert store.get(ev.alert_id) == ev
            assert svc.handle(fake_alert(), "not an image", []) is None  # renderer blows up
            assert q.empty()

    asyncio.run(go())


def sse_req(store, bus, last_id=None):
    class Src:
        camera_id = "cam1"

        def stats(self):
            return SourceStats(
                camera_id="cam1", fps=1.0, width=1, height=1, decode_ms=1.0,
                frames_total=1, frames_dropped=0,
            )  # fmt: skip

    st = SimpleNamespace(source=Src(), bus=bus, alert_store=store)
    headers = {"last-event-id": last_id} if last_id else {}
    return SimpleNamespace(app=SimpleNamespace(state=st), headers=headers)


def test_sse_live_alert_has_id(tmp_path):
    bus = EventBus()

    async def go():
        bus.bind(asyncio.get_running_loop())
        r = await events(sse_req(AlertStore(tmp_path, 7), bus), camera_id="cam1")
        assert (await anext(r.body_iterator)).startswith("event: stats")
        bus.publish(mk("a1", camera_id="other"))  # other camera: filtered
        bus.publish(mk("a2"))
        out = await anext(r.body_iterator)
        assert out.startswith("id: a2\nevent: alert\n")
        assert json.loads(out.split("data: ")[1])["alert_id"] == "a2"
        await r.body_iterator.aclose()

    asyncio.run(go())


def test_sse_last_event_id_replays_newer_oldest_first(tmp_path):
    store, bus = AlertStore(tmp_path, 7), EventBus()
    for i in ("a1", "a2", "a3"):
        store.save(mk(i), JPEG)

    async def go():
        bus.bind(asyncio.get_running_loop())
        r = await events(sse_req(store, bus, "a1"), camera_id="cam1")
        ids = []
        for _ in range(3):  # 2 replays, then stats
            ids.append((await anext(r.body_iterator)).split("\n")[0])
        assert ids == ["id: a2", "id: a3", "event: stats"]
        bus.publish(mk("a3"))  # duplicate of a replayed alert
        bus.publish(mk("a4"))
        out = await anext(r.body_iterator)
        assert out.startswith("id: a4\n")
        await r.body_iterator.aclose()

    asyncio.run(go())


def client(store=None):
    app = FastAPI()
    app.include_router(router)
    if store:
        app.state.alert_store = store
    return TestClient(app)


def test_rest_endpoints(tmp_path):
    s = AlertStore(tmp_path, 7)
    s.save(mk("a1"), JPEG)
    s.save(mk("a2", camera_id="cam2"), JPEG)
    s.save(mk("a3"), JPEG)
    c = client(s)
    assert [a["alert_id"] for a in c.get("/api/alerts").json()] == ["a3", "a2", "a1"]
    assert [a["alert_id"] for a in c.get("/api/alerts?limit=1").json()] == ["a3"]
    assert [a["alert_id"] for a in c.get("/api/alerts?camera_id=cam2").json()] == ["a2"]
    r = c.get("/api/alerts/a1/snapshot.jpg")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert r.content == JPEG
    assert c.get("/api/alerts/ffff/snapshot.jpg").status_code == 404
    for bad in ("..%2Fx", "..%5Cx", "%2E%2E%2Falert.json", "A1", "a" * 40):
        assert c.get(f"/api/alerts/{bad}/snapshot.jpg").status_code == 404


def test_rest_without_store():
    c = client()
    assert c.get("/api/alerts").json() == []
    assert c.get("/api/alerts/a1/snapshot.jpg").status_code == 404
