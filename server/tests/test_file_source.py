import shutil
import time

import av
import numpy as np
import pytest

from app.sources import FileFrameSource

FPS, W, H = 20, 64, 48


@pytest.fixture
def mp4(tmp_path):
    path = str(tmp_path / "t.mp4")
    with av.open(path, "w") as out:
        s = out.add_stream("mpeg4", rate=FPS)
        s.width, s.height, s.pix_fmt = W, H, "yuv420p"
        for i in range(10):  # 0.5 s clip, so looping is exercised
            img = np.full((H, W, 3), i * 20, np.uint8)
            for p in s.encode(av.VideoFrame.from_ndarray(img, format="bgr24")):
                out.mux(p)
        for p in s.encode():
            out.mux(p)
    return path


def test_frames_size_fps_and_loop(mp4):
    src = FileFrameSource("camX", mp4)
    src.start()
    time.sleep(2.5)
    st = src.stats()
    f = src.latest()
    src.stop()
    assert f.camera_id == "camX" and f.image.shape == (H, W, 3)
    assert (st.width, st.height) == (W, H)
    assert st.frames_total > 10  # looped past the 10-frame clip
    assert abs(st.fps - FPS) < 4
    assert 0 < st.decode_ms < 50
    assert st.frames_dropped > 0  # nobody read until the end


def test_stop_is_prompt(mp4):
    src = FileFrameSource("camX", mp4)
    src.start()
    time.sleep(0.3)
    t0 = time.monotonic()
    src.stop()
    assert time.monotonic() - t0 < 1 and not src._thread.is_alive()


def test_file_retries_then_recovers(mp4, tmp_path):
    path = tmp_path / "late.mp4"  # does not exist yet: av.open raises, source must survive
    src = FileFrameSource("camX", str(path))
    src.start()
    time.sleep(0.5)
    assert src._thread.is_alive() and src.stats().frames_total == 0
    shutil.copy(mp4, path)  # first retry is after 1 s
    time.sleep(2)
    assert src.stats().frames_total > 0
    src.stop()


def test_source_ts_monotonic_and_matches_video_time(mp4):
    src = FileFrameSource("camX", mp4, loop=False, realtime=False)
    got = []
    src.on_frame = got.append
    src.start()
    assert src.ended.wait(5)
    ts = [f.src_ts for f in got]
    assert len(ts) == 10
    assert ts == sorted(ts) and len(set(ts)) == 10
    assert ts == pytest.approx([i / FPS for i in range(10)], abs=1e-3)
    assert src.error is None


def test_looping_source_ts_stays_monotonic(mp4):
    src = FileFrameSource("camX", mp4, realtime=False)
    got = []
    src.on_frame = got.append
    src.start()
    time.sleep(0.5)
    src.stop()
    ts = [f.src_ts for f in got]
    assert len(ts) > 10 and all(b > a for a, b in zip(ts, ts[1:], strict=False))


def test_non_looping_realtime_ends_and_paces(mp4):
    src = FileFrameSource("camX", mp4, loop=False)
    t0 = time.monotonic()
    src.start()
    assert src.ended.wait(5)
    assert 0.35 < time.monotonic() - t0 < 1.5  # 10 frames at 20 fps
    assert src.stats().frames_total == 10


def test_fast_mode_beats_realtime_with_same_timestamps(tmp_path):
    path = str(tmp_path / "long.mp4")
    with av.open(path, "w") as out:
        s = out.add_stream("mpeg4", rate=FPS)
        s.width, s.height, s.pix_fmt = W, H, "yuv420p"
        for _ in range(100):  # 5 s of video
            for p in s.encode(av.VideoFrame.from_ndarray(np.zeros((H, W, 3), np.uint8), "bgr24")):
                out.mux(p)
        for p in s.encode():
            out.mux(p)
    src = FileFrameSource("camX", path, loop=False, realtime=False)
    got = []
    src.on_frame = got.append
    t0 = time.monotonic()
    src.start()
    assert src.ended.wait(5)
    assert time.monotonic() - t0 < 2.5  # 5 s of video
    assert got[-1].src_ts == pytest.approx(99 / FPS, abs=1e-3)


def test_missing_file_ends_with_error_when_not_looping(tmp_path):
    src = FileFrameSource("camX", str(tmp_path / "nope.mp4"), loop=False)
    src.start()
    assert src.ended.wait(5) and src.error is not None
