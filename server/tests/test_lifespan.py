"""App startup: alert storage failures, the hourly purge and config warnings."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from app.detection.base import FakeDetector
from app.main import app
from tests.test_alerts import JPEG, mk
from tests.test_eval import make_clip

TRIANGLE = [[0, 0], [1, 0], [1, 1]]


@pytest.fixture
def env(tmp_path, monkeypatch):
    make_clip(tmp_path / "c.mp4")
    monkeypatch.setenv("SOURCE_URL", str(tmp_path / "c.mp4"))
    monkeypatch.setenv("ALERTS_DIR", str(tmp_path / "alerts"))
    monkeypatch.setenv("DETECTOR", "none")
    zones = tmp_path / "zones.json"
    zones.write_text(json.dumps({"cam1": [{"name": "door", "polygon": TRIANGLE, "dwell_s": 1}]}))
    monkeypatch.setenv("ZONES_PATH", str(zones))
    return tmp_path


def wait_for(cond):
    deadline = time.monotonic() + 5
    while not cond() and time.monotonic() < deadline:
        time.sleep(0.02)
    return cond()


def test_unusable_alerts_dir_disables_alerts_only(env, monkeypatch):
    (env / "file").write_text("x")
    monkeypatch.setenv("ALERTS_DIR", str(env / "file"))  # a file, so mkdir fails
    monkeypatch.setenv("DETECTOR", "yolo")
    monkeypatch.setattr("app.main.YoloDetector", lambda cfg: FakeDetector())
    with TestClient(app) as c:
        assert wait_for(lambda: app.state.pipeline.stats().inference_ms_p50 is not None)
        assert app.state.source.stats().frames_total > 0
        assert c.get("/api/alerts").json() == []


def test_expired_alerts_are_purged_while_running(env, monkeypatch):
    monkeypatch.setattr("app.main.PURGE_INTERVAL_S", 0.05, raising=False)
    with TestClient(app):
        store = app.state.alert_store
        store.save(mk("a1", ts=0), JPEG)
        assert wait_for(lambda: store.get("a1") is None)


def test_warns_once_when_no_zone_has_dwell(env, caplog):
    with TestClient(app):
        pass
    assert "can never fire" not in caplog.text
    (env / "zones.json").write_text(json.dumps({"cam1": [{"name": "door", "polygon": TRIANGLE}]}))
    with TestClient(app):
        pass
    assert caplog.text.count("can never fire") == 1
