import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.events import StatsEvent, format_sse

router = APIRouter()


@router.get("/api/events")
async def events(request: Request, camera_id: str):
    # One source per process for now; an unknown camera_id is a 404 rather than a silent stream.
    source = request.app.state.source
    if camera_id != source.camera_id:
        raise HTTPException(404, f"unknown camera_id {camera_id!r}")

    async def stream():
        # Starlette cancels this generator on client disconnect, ending the loop.
        while True:
            yield format_sse("stats", StatsEvent(**source.stats()))
            await asyncio.sleep(1)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )
