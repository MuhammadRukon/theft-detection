import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    camera_id: str = field(default_factory=lambda: os.getenv("CAMERA_ID", "cam1"))
    # rtsp:// URL, or a path to an mp4 (looped) for tests.
    source_url: str = field(
        default_factory=lambda: os.getenv("SOURCE_URL", "rtsp://127.0.0.1:8554/cam1")
    )
