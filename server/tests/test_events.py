import asyncio
import json
import threading
from dataclasses import asdict
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.events import events
from app.events import DetectionsEvent, EventBus, StatsEvent, Track, format_sse
from app.sources.base import SourceStats

STATS = dict(
    camera_id="cam1", fps=15.0, width=1280, height=720,
    decode_ms=1.5, frames_total=30, frames_dropped=2,
)  # fmt: skip
PIPELINE_NONE = dict(
    inference_fps=None, inference_ms_p50=None, inference_ms_p95=None, e2e_latency_ms=None
)


def test_format_sse():
    out = format_sse("stats", StatsEvent(**STATS))
    head, data = out.rstrip("\n").split("\n")
    assert head == "event: stats"
    assert out.endswith("\n\n")
    assert json.loads(data.removeprefix("data: ")) == {**STATS, **PIPELINE_NONE}


def test_format_sse_id():
    assert format_sse("stats", StatsEvent(**STATS), id="7").startswith("id: 7\nevent: stats\n")


def test_route():
    class Src:
        camera_id = "cam1"

        def stats(self):
            return SourceStats(**STATS)

    bus = EventBus()
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(source=Src(), bus=bus)))

    det = DetectionsEvent(camera_id="cam1", frame_ts=1.0, latency_ms=2.0, tracks=[])

    async def go():
        bus.bind(asyncio.get_running_loop())
        with pytest.raises(HTTPException) as e:
            await events(req, camera_id="nope")
        assert e.value.status_code == 404
        r = await events(req, camera_id="cam1")
        assert r.media_type == "text/event-stream"
        assert (await anext(r.body_iterator)).startswith("event: stats")
        bus.publish(det.model_copy(update={"camera_id": "other"}))  # filtered out
        bus.publish(det)
        out = await anext(r.body_iterator)
        assert out.startswith("event: detections") and '"camera_id":"cam1"' in out
        assert len(bus._subs) == 1
        await r.body_iterator.aclose()  # what Starlette does on disconnect

    asyncio.run(go())


def test_schema_pre_first_frame():
    assert StatsEvent(**{**STATS, "width": None, "height": None, "decode_ms": None}).width is None


def test_source_stats_matches_event_schema():
    assert (
        asdict(SourceStats(**STATS))
        == STATS
        == StatsEvent(**STATS).model_dump(exclude=set(PIPELINE_NONE))
    )


def test_format_sse_detections_uses_class_key():
    t = Track(track_id=3, class_name="person", conf=0.9, x1=0.1, y1=0.2, x2=0.3, y2=0.4)
    e = DetectionsEvent(camera_id="c", frame_ts=1, latency_ms=2, tracks=[t])
    out = format_sse("detections", e)
    assert out.startswith("event: detections\n")
    assert json.loads(out.split("data: ")[1])["tracks"][0] == {
        "track_id": 3, "class": "person", "conf": 0.9, "x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.4,
    }  # fmt: skip


def test_stats_new_fields_default_none():
    e = StatsEvent(**STATS)
    assert e.inference_fps is e.inference_ms_p50 is e.inference_ms_p95 is e.e2e_latency_ms is None


def ev(n):
    return StatsEvent(**{**STATS, "frames_total": n})


def test_bus_drop_oldest():
    async def go():
        bus = EventBus(maxsize=2)
        bus.bind(asyncio.get_running_loop())
        with bus.subscribe() as q:
            for n in (1, 2, 3):
                bus.publish(ev(n))
            await asyncio.sleep(0)
            assert [q.get_nowait().frames_total, q.get_nowait().frames_total] == [2, 3]

    asyncio.run(go())


def test_bus_publish_from_thread():
    async def go():
        bus = EventBus()
        bus.bind(asyncio.get_running_loop())
        with bus.subscribe() as q:
            threading.Thread(target=bus.publish, args=(ev(1),)).start()
            assert (await asyncio.wait_for(q.get(), 2)).frames_total == 1

    asyncio.run(go())


def test_bus_publish_before_bind_is_noop():
    async def go():
        bus = EventBus()
        with bus.subscribe() as q:
            bus.publish(ev(1))
            await asyncio.sleep(0)
            assert q.empty()

    asyncio.run(go())


def test_bus_unsubscribe_stops_delivery():
    async def go():
        bus = EventBus()
        bus.bind(asyncio.get_running_loop())
        with bus.subscribe() as q:
            pass
        bus.publish(ev(1))
        await asyncio.sleep(0)
        assert q.empty() and not bus._subs

    asyncio.run(go())


def test_route_merges_pipeline_stats():
    from app.pipeline import PipelineStats

    class Src:
        camera_id = "cam1"

        def stats(self):
            return SourceStats(**STATS)

    class Pipe:
        def stats(self):
            return PipelineStats(5.0, 30.0, 40.0, 120.0)

    state = SimpleNamespace(source=Src(), bus=EventBus(), pipeline=Pipe())
    req = SimpleNamespace(app=SimpleNamespace(state=state))

    async def go():
        r = await events(req, camera_id="cam1")
        out = await anext(r.body_iterator)
        await r.body_iterator.aclose()
        return out

    d = json.loads(asyncio.run(go()).split("data: ")[1])
    assert (d["fps"], d["inference_fps"], d["inference_ms_p95"], d["e2e_latency_ms"]) == (
        15.0, 5.0, 40.0, 120.0,
    )  # fmt: skip
