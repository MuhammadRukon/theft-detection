from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/api/zones")
def zones(request: Request, camera_id: str):
    # Read-only view of the zones the behavior engine loaded; one camera per process for now.
    if camera_id != request.app.state.source.camera_id:
        raise HTTPException(404, f"unknown camera_id {camera_id!r}")
    return [
        {"name": z.name, "polygon": [list(p) for p in z.polygon], "dwell_s": z.dwell_s}
        for z in getattr(request.app.state, "zones", [])
    ]
