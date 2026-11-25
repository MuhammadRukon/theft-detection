import av
import pytest

from app.sources import FileFrameSource, RtspFrameSource, make_source


def test_make_source_dispatch(tmp_path):
    f = tmp_path / "a.mp4"
    f.write_bytes(b"")
    assert isinstance(make_source("c", "rtsp://host/x"), RtspFrameSource)
    assert isinstance(make_source("c", str(f)), FileFrameSource)


def test_make_source_rejects_missing_file(tmp_path):
    with pytest.raises(ValueError):
        make_source("c", str(tmp_path / "typo.mp4"))


def test_rtsp_retries_after_unexpected_error(monkeypatch):
    src = RtspFrameSource("c", "rtsp://x")
    calls = []

    def fake_open(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("boom")
        src._stop.set()
        raise OSError("down")

    monkeypatch.setattr(av, "open", fake_open)
    src._run()
    assert len(calls) == 2
