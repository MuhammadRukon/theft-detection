"""Source time on live (RTSP) sources, driven by fake containers and frames."""

import threading
from types import SimpleNamespace

import numpy as np
import pytest

from app.sources import FileFrameSource, RtspFrameSource

IMG = np.zeros((4, 4, 3), np.uint8)


def frame(t):
    """A decoded frame at `t` seconds; None means it carries no pts."""
    return SimpleNamespace(
        pts=None if t is None else int(t * 1000), time=t, to_ndarray=lambda format: IMG
    )


class Container:
    def __init__(self, times):
        self.times = times

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def demux(self, video):
        return [SimpleNamespace(decode=lambda: [frame(t) for t in self.times])]


def test_reconnect_adds_the_outage_to_source_time():
    sessions, got, done = [[0.0, 0.2], [0.0, 0.2]], [], threading.Event()

    class Src(RtspFrameSource):
        def _open(self):
            return Container(sessions.pop(0) if sessions else [])

    src = Src("camX", "rtsp://x")

    def on_frame(f):
        got.append(f.src_ts)
        if len(got) == 4:
            done.set()

    src.on_frame = on_frame
    src.start()  # first stream ends, reader backs off 1 s, then reconnects
    assert done.wait(5)
    src.stop()
    assert got[2] - got[1] >= 0.9
    assert got[3] - got[2] == pytest.approx(0.2)


def test_file_reopen_ignores_wall_clock(monkeypatch):
    now = [0.0]
    monkeypatch.setattr("app.sources.base.time.monotonic", lambda: now[0])
    src = FileFrameSource("camX", "x.mp4")
    assert src._source_ts(frame(0.0)) == 0
    now[0] = 100.0
    src._new_session()
    assert src._source_ts(frame(0.0)) == pytest.approx(0.001)


def test_one_clock_per_session_and_never_backwards(monkeypatch):
    now = [5000.0]
    monkeypatch.setattr("app.sources.base.time.monotonic", lambda: now[0])

    def stamps(times):
        src, out = RtspFrameSource("camX", "rtsp://x"), []
        for t in times:
            now[0] += 0.2
            out.append(src._source_ts(frame(t)))
        return out

    # pts session: a frame without pts must not switch to the monotonic clock
    assert stamps([10.0, 10.2, None, 10.6]) == pytest.approx([0, 0.2, 0.2, 0.6])
    # no pts on the first frame: monotonic for the whole session, later pts ignored
    assert stamps([None, 90.0, None]) == pytest.approx([0, 0.2, 0.4])
    # camera timestamp reset: hold, then keep advancing
    assert stamps([10.0, 11.0, 2.0, 3.0]) == pytest.approx([0, 1, 1, 2])
