import time

import av

from app.sources.base import FrameSource


class FileFrameSource(FrameSource):
    """Loops an mp4, paced at the file's native fps."""

    def __init__(self, camera_id: str, path: str):
        super().__init__(camera_id)
        self.path = path

    def _run(self) -> None:
        while not self._stop.is_set():
            with av.open(self.path) as container:
                stream = container.streams.video[0]
                period = 1 / float(stream.average_rate or 30)
                deadline = time.monotonic()
                for packet in container.demux(stream):
                    t0 = time.perf_counter()
                    for frame in packet.decode():
                        self._emit(frame, (time.perf_counter() - t0) * 1000)
                        deadline += period
                        if self._stop.wait(max(0.0, deadline - time.monotonic())):
                            return
