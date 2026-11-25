import subprocess
import sys
import time

import numpy as np

from app.config import Settings
from app.detection.base import Detection, FakeDetector

IMG = np.zeros((720, 1280, 3), np.uint8)
D = Detection(0, "person", 0.9, 10, 20, 110, 220)


def test_fake_returns_configured_detections_copy():
    f = FakeDetector([D])
    out = f.detect(IMG)
    assert out == [D]
    out.clear()
    assert f.detect(IMG) == [D] and f.calls == 2


def test_fake_default_empty():
    assert FakeDetector().detect(IMG) == []


def test_fake_delay():
    t = time.perf_counter()
    FakeDetector(delay_s=0.05).detect(IMG)
    assert time.perf_counter() - t >= 0.05


def test_settings_defaults():
    s = Settings()
    assert s.model_path.endswith("yolo11n.pt") and s.detect_conf == 0.2
    assert s.track_conf == 0.4
    assert s.torch_threads == 4 and s.inference_fps == 5.0


def test_import_does_not_load_torch():
    code = "import sys, app.detection.yolo; assert 'torch' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True)


def test_missing_model_raises_before_importing(tmp_path):
    # Subprocess, like the import test: proves the guard runs before torch/ultralytics are
    # imported, and it cannot touch this network-less test if it ever did try to download.
    missing = tmp_path / "nope.pt"
    code = (
        "import dataclasses, sys, app.config as c, app.detection.yolo as y\n"
        f"path = {str(missing)!r}\n"
        "s = dataclasses.replace(c.Settings(), model_path=path)\n"
        "try:\n"
        "    y.YoloDetector(s)\n"
        "except FileNotFoundError as e:\n"
        f"    assert path in str(e), e\n"
        "else:\n"
        "    raise SystemExit('no FileNotFoundError')\n"
        "assert 'torch' not in sys.modules, 'torch imported before check'\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
