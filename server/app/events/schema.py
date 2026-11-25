from pydantic import BaseModel, ConfigDict, Field


class StatsEvent(BaseModel):
    camera_id: str
    fps: float
    # None until the first frame is decoded
    width: int | None
    height: int | None
    decode_ms: float | None
    frames_total: int
    frames_dropped: int
    # None until the detection pipeline has produced a result
    inference_fps: float | None = None
    inference_ms_p50: float | None = None
    inference_ms_p95: float | None = None
    e2e_latency_ms: float | None = None


class Track(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    track_id: int
    class_name: str = Field(alias="class")
    conf: float
    # normalized 0-1
    x1: float
    y1: float
    x2: float
    y2: float


class DetectionsEvent(BaseModel):
    camera_id: str
    frame_ts: float
    latency_ms: float
    tracks: list[Track]
