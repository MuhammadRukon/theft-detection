import time

import av

from app.sources.base import FrameSource


class FileFrameSource(FrameSource):
    """Replays an mp4. Source timestamps always come from the video, whatever the pacing.

    Default (dev): loops, paced at the file's native fps.
    `loop=False`: plays once, then `ended` is set (a failure sets `ended` and `error` instead).
    `realtime=False`: no pacing, decodes as fast as possible (replay/eval).
    """

    def __init__(self, camera_id: str, path: str, loop: bool = True, realtime: bool = True):
        super().__init__(camera_id)
        self.path = path
        self.loop_on_end = loop
        self.stop_on_end = not loop
        self.realtime = realtime

    def _open(self):
        container = av.open(self.path)
        self._period = 1 / float(container.streams.video[0].average_rate or 30)
        self._deadline = time.monotonic()
        return container

    def _pace(self, frame) -> bool:
        if not self.realtime:
            return self._stop.is_set()
        self._deadline += self._period
        return self._stop.wait(max(0.0, self._deadline - time.monotonic()))
