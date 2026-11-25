import asyncio
import json
from dataclasses import asdict
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.events import events
from app.events import StatsEvent, format_sse
from app.sources.base import SourceStats

STATS = dict(
    camera_id="cam1", fps=15.0, width=1280, height=720,
    decode_ms=1.5, frames_total=30, frames_dropped=2,
)  # fmt: skip


def test_format_sse():
    out = format_sse("stats", StatsEvent(**STATS))
    head, data = out.rstrip("\n").split("\n")
    assert head == "event: stats"
    assert out.endswith("\n\n")
    assert json.loads(data.removeprefix("data: ")) == STATS


def test_format_sse_id():
    assert format_sse("stats", StatsEvent(**STATS), id="7").startswith("id: 7\nevent: stats\n")


def test_route():
    class Src:
        camera_id = "cam1"

        def stats(self):
            return SourceStats(**STATS)

    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(source=Src())))

    async def go():
        with pytest.raises(HTTPException) as e:
            await events(req, camera_id="nope")
        assert e.value.status_code == 404
        r = await events(req, camera_id="cam1")
        assert r.media_type == "text/event-stream"
        assert (await anext(r.body_iterator)).startswith("event: stats")
        await r.body_iterator.aclose()  # what Starlette does on disconnect

    asyncio.run(go())


def test_schema_pre_first_frame():
    assert StatsEvent(**{**STATS, "width": None, "height": None, "decode_ms": None}).width is None


def test_source_stats_matches_event_schema():
    assert asdict(SourceStats(**STATS)) == STATS == StatsEvent(**STATS).model_dump()
