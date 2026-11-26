import asyncio
import time
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from app.alerts import valid_alert_id
from app.events import AlertEvent, DetectionsEvent, StatsEvent, format_sse

router = APIRouter()


@router.get("/api/events")
async def events(request: Request, camera_id: str):
    # One source per process for now; an unknown camera_id is a 404 rather than a silent stream.
    source = request.app.state.source
    pipeline = getattr(request.app.state, "pipeline", None)
    if camera_id != source.camera_id:
        raise HTTPException(404, f"unknown camera_id {camera_id!r}")

    store = getattr(request.app.state, "alert_store", None)
    last_id = getattr(request, "headers", {}).get("last-event-id")

    async def stream():
        # Starlette cancels/closes this generator on client disconnect; `with` then unsubscribes.
        with request.app.state.bus.subscribe() as q:
            seen: set[str] = set()
            if store and last_id and valid_alert_id(last_id):
                # subscribed first, so nothing published during replay is lost; `seen` dedupes
                missed = [a for a in store.list(10_000) if a.alert_id > last_id]
                for a in reversed(missed):
                    if a.camera_id == camera_id:
                        seen.add(a.alert_id)
                        yield format_sse("alert", a, id=a.alert_id)
            next_stats = 0.0
            while True:
                if time.monotonic() >= next_stats:
                    pipe = asdict(pipeline.stats()) if pipeline else {}
                    if pipe:
                        pipe["pipeline_status"] = pipe.pop("status")
                    yield format_sse("stats", StatsEvent(**asdict(source.stats()), **pipe))
                    next_stats = time.monotonic() + 1
                try:
                    ev = await asyncio.wait_for(q.get(), max(next_stats - time.monotonic(), 0))
                except TimeoutError:
                    continue
                if isinstance(ev, DetectionsEvent) and ev.camera_id == camera_id:
                    yield format_sse("detections", ev)
                elif isinstance(ev, AlertEvent) and ev.camera_id == camera_id:
                    if ev.alert_id not in seen:
                        yield format_sse("alert", ev, id=ev.alert_id)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


@router.get("/api/alerts")
def list_alerts(
    request: Request, limit: int = Query(50, ge=1, le=500), camera_id: str | None = None
):
    store = getattr(request.app.state, "alert_store", None)
    if store is None:
        return []
    alerts = store.list(10_000 if camera_id else limit)
    return [a for a in alerts if camera_id in (None, a.camera_id)][:limit]


@router.get("/api/alerts/{alert_id}/snapshot.jpg")
def alert_snapshot(request: Request, alert_id: str):
    store = getattr(request.app.state, "alert_store", None)
    path = store.snapshot_path(alert_id) if store and valid_alert_id(alert_id) else None
    if path is None:
        raise HTTPException(404, "unknown alert")
    try:  # read here: the purge may delete the file at any moment
        jpeg = path.read_bytes()
    except OSError:
        raise HTTPException(404, "snapshot missing") from None
    return Response(jpeg, media_type="image/jpeg")
