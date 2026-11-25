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
