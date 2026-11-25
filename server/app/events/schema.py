from pydantic import BaseModel


class StatsEvent(BaseModel):
    camera_id: str
    fps: float
    # None until the first frame is decoded
    width: int | None
    height: int | None
    decode_ms: float | None
    frames_total: int
    frames_dropped: int
