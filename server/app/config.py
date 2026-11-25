import os
from dataclasses import dataclass, field
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent


def _zones_path() -> str:
    # ZONES_PATH wins; else the real file if present, else the committed sample.
    if env := os.getenv("ZONES_PATH"):
        return env
    real = SERVER_DIR / "config" / "zones.json"
    return str(real if real.is_file() else SERVER_DIR / "config" / "zones.sample.json")


@dataclass(frozen=True)
class Settings:
    camera_id: str = field(default_factory=lambda: os.getenv("CAMERA_ID", "cam1"))
    # rtsp:// URL, or a path to an mp4 (looped) for tests.
    source_url: str = field(
        default_factory=lambda: os.getenv("SOURCE_URL", "rtsp://127.0.0.1:8554/cam1")
    )
    model_path: str = field(
        default_factory=lambda: os.getenv("MODEL_PATH", str(SERVER_DIR / "models" / "yolo11n.pt"))
    )
    # YOLO conf floor; low so ByteTrack's second stage sees weak boxes. Track start uses track_conf.
    detect_conf: float = field(default_factory=lambda: float(os.getenv("DETECT_CONF", "0.2")))
    track_conf: float = field(default_factory=lambda: float(os.getenv("TRACK_CONF", "0.4")))
    torch_threads: int = field(default_factory=lambda: int(os.getenv("TORCH_THREADS", "4")))
    inference_fps: float = field(default_factory=lambda: float(os.getenv("INFERENCE_FPS", "5.0")))
    # "yolo", or "none" to run ingest/SSE without a model (tests, dev).
    detector: str = field(default_factory=lambda: os.getenv("DETECTOR", "yolo"))
    zones_path: str = field(default_factory=_zones_path)
