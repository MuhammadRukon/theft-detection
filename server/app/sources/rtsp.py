import logging
import time

import av

from app.sources.base import FrameSource

log = logging.getLogger(__name__)

OPTIONS = {"rtsp_transport": "tcp", "fflags": "nobuffer", "flags": "low_delay"}


class RtspFrameSource(FrameSource):
    def __init__(self, camera_id: str, url: str):
        super().__init__(camera_id)
        self.url = url

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                # timeout (s) bounds connect and reads so stop() is never stuck long.
                with av.open(self.url, options=OPTIONS, timeout=5.0) as container:
                    log.info("%s: connected to %s", self.camera_id, self.url)
                    backoff = 1.0
                    for packet in container.demux(video=0):
                        if self._stop.is_set():
                            return
                        t0 = time.perf_counter()
                        for frame in packet.decode():
                            self._emit(frame, (time.perf_counter() - t0) * 1000)
                    log.warning("%s: stream ended", self.camera_id)
            except (av.FFmpegError, OSError) as e:
                log.warning("%s: unavailable (%s), retry in %.0fs", self.camera_id, e, backoff)
            except Exception:
                log.exception("%s: reader error, retry in %.0fs", self.camera_id, backoff)
            self._stop.wait(backoff)
            backoff = min(backoff * 2, 10.0)
