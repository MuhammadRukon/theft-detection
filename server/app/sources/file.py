import time

import av

from app.sources.base import FrameSource


class FileFrameSource(FrameSource):
    """Loops an mp4, paced at the file's native fps."""

    loop_on_end = True

    def __init__(self, camera_id: str, path: str):
        super().__init__(camera_id)
        self.path = path

    def _open(self):
        container = av.open(self.path)
        self._period = 1 / float(container.streams.video[0].average_rate or 30)
        self._deadline = time.monotonic()
        return container

    def _pace(self, frame) -> bool:
        self._deadline += self._period
        return self._stop.wait(max(0.0, self._deadline - time.monotonic()))
