from pathlib import Path

from app.sources.base import Frame, FrameSource
from app.sources.file import FileFrameSource
from app.sources.rtsp import RtspFrameSource

__all__ = ["FileFrameSource", "Frame", "FrameSource", "RtspFrameSource", "make_source"]


def make_source(camera_id: str, url: str) -> FrameSource:
    if url.startswith("rtsp://"):
        return RtspFrameSource(camera_id, url)
    if not Path(url).is_file():
        raise ValueError(f"{camera_id}: source must be rtsp:// or an existing file, got {url!r}")
    return FileFrameSource(camera_id, url)
