import logging

import av

from app.sources.base import FrameSource

log = logging.getLogger(__name__)

OPTIONS = {"rtsp_transport": "tcp", "fflags": "nobuffer", "flags": "low_delay"}


class RtspFrameSource(FrameSource):
    """Source time comes from packet pts, or monotonic time if a session's first frame has none;
    reconnect outages are included (see FrameSource._source_ts)."""

    def __init__(self, camera_id: str, url: str):
        super().__init__(camera_id)
        self.url = url

    def _open(self):
        # timeout (s) bounds connect and reads so stop() is never stuck long.
        container = av.open(self.url, options=OPTIONS, timeout=5.0)
        log.info("%s: connected to %s", self.camera_id, self.url)
        return container
