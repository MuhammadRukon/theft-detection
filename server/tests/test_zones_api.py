from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.zones import router
from app.behavior import Zone


def client(zones=None):
    app = FastAPI()
    app.include_router(router)
    app.state.source = SimpleNamespace(camera_id="cam1")
    if zones is not None:
        app.state.zones = zones
    return TestClient(app)


def test_returns_loaded_zones():
    c = client([Zone("door", ((0.1, 0.2), (0.9, 0.2), (0.5, 0.8)), 10.0)])
    r = c.get("/api/zones", params={"camera_id": "cam1"})
    assert r.status_code == 200
    assert r.json() == [
        {"name": "door", "polygon": [[0.1, 0.2], [0.9, 0.2], [0.5, 0.8]], "dwell_s": 10.0}
    ]


def test_empty_when_none_loaded():
    assert client().get("/api/zones", params={"camera_id": "cam1"}).json() == []
    assert client([]).get("/api/zones", params={"camera_id": "cam1"}).json() == []


def test_unknown_camera_404():
    assert client([]).get("/api/zones", params={"camera_id": "nope"}).status_code == 404
