import os
from dataclasses import dataclass, field
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent


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
    detect_conf: float = field(default_factory=lambda: float(os.getenv("DETECT_CONF", "0.4")))
    torch_threads: int = field(default_factory=lambda: int(os.getenv("TORCH_THREADS", "4")))
    inference_fps: float = field(default_factory=lambda: float(os.getenv("INFERENCE_FPS", "5.0")))
    # "yolo", or "none" to run ingest/SSE without a model (tests, dev).
    detector: str = field(default_factory=lambda: os.getenv("DETECTOR", "yolo"))
