import asyncio
import time
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.events import DetectionsEvent, StatsEvent, format_sse

router = APIRouter()


@router.get("/api/events")
async def events(request: Request, camera_id: str):
    # One source per process for now; an unknown camera_id is a 404 rather than a silent stream.
    source = request.app.state.source
    pipeline = getattr(request.app.state, "pipeline", None)
    if camera_id != source.camera_id:
        raise HTTPException(404, f"unknown camera_id {camera_id!r}")

    async def stream():
        # Starlette cancels/closes this generator on client disconnect; `with` then unsubscribes.
        with request.app.state.bus.subscribe() as q:
            next_stats = 0.0
            while True:
                if time.monotonic() >= next_stats:
                    pipe = asdict(pipeline.stats()) if pipeline else {}
                    yield format_sse("stats", StatsEvent(**asdict(source.stats()), **pipe))
                    next_stats = time.monotonic() + 1
                try:
                    ev = await asyncio.wait_for(q.get(), max(next_stats - time.monotonic(), 0))
                except TimeoutError:
                    continue
                if isinstance(ev, DetectionsEvent) and ev.camera_id == camera_id:
                    yield format_sse("detections", ev)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )
