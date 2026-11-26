import json
from types import SimpleNamespace

import av
import numpy as np
import pytest

from app.behavior import Zone
from app.config import Settings
from app.detection.base import Detection, FakeDetector
from tools.eval import LabelError, count_id_switches, load_expected, main, run_clip, score

FPS, W, H = 20, 64, 48
E = {"type": "dwell", "zone": "door", "at_s": 10}


def make_clip(path, seconds=2):
    with av.open(str(path), "w") as out:
        s = out.add_stream("mpeg4", rate=FPS)
        s.width, s.height, s.pix_fmt = W, H, "yuv420p"
        for _ in range(FPS * seconds):
            for p in s.encode(av.VideoFrame.from_ndarray(np.zeros((H, W, 3), np.uint8), "bgr24")):
                out.mux(p)
        for p in s.encode():
            out.mux(p)


def label(path, expected):
    path.write_text(json.dumps({"expected_alerts": expected, "notes": ""}))


def alert(t, zone="door"):
    return SimpleNamespace(type="dwell", zone=zone, src_ts=t)


def test_score_rules():
    assert score("c", [E], [alert(11)]).passed
    r = score("c", [E], [alert(10.5), alert(12)])  # one repeat allowed
    assert r.passed and r.repeats == 1 and r.delays == [0.5]
    assert score("c", [E], [alert(10.5), alert(12), alert(14)]).false_alarms == 1
    assert score("c", [E], [alert(13.5)]).missed == 1  # too late
    early = score("c", [E], [alert(9)])  # too early: missed, and the alert is false
    assert early.missed == 1 and early.false_alarms == 1
    assert score("c", [E], [alert(11, zone="x")]).missed == 1
    assert score("c", [], [alert(1)]).false_alarms == 1
    assert score("c", [], []).passed


def test_score_without_zone_matches_only_null_zone_alerts():
    for e in ({"type": "dwell", "at_s": 10}, {"type": "dwell", "zone": None, "at_s": 10}):
        assert score("c", [e], [alert(11, zone=None)]).passed
        r = score("c", [e], [alert(11, zone="door")])
        assert r.missed == 1 and r.false_alarms == 1
    assert score("c", [E], [alert(11, zone=None)]).missed == 1


def test_id_switches():
    def ev(*ids):
        return SimpleNamespace(tracks=[SimpleNamespace(track_id=i) for i in ids])

    assert count_id_switches([ev(1), ev(2), ev()]) == 1
    assert count_id_switches([ev(1, 2), ev(1, 2)]) == 0
    assert count_id_switches([]) == 0


def test_run_clip_subsamples_by_video_time(tmp_path):
    make_clip(tmp_path / "a.mp4", seconds=2)
    det = FakeDetector([Detection(0, "person", 0.9, 5, 5, 30, 40)])
    alerts, events = run_clip(tmp_path / "a.mp4", det, Settings(inference_fps=5.0))
    assert alerts == [] and det.calls == 10 and len(events) == 10  # not all 40 frames


def test_main_normal_clip_passes_and_missed_alert_fails(tmp_path, capsys):
    make_clip(tmp_path / "normal.mp4")
    label(tmp_path / "normal.json", [])
    assert main(["--clips", str(tmp_path), "--detector", "fake"]) == 0
    assert "PASS" in capsys.readouterr().out

    make_clip(tmp_path / "theft.mp4")
    label(tmp_path / "theft.json", [E])
    assert main(["--clips", str(tmp_path), "--detector", "fake"]) == 1
    out = capsys.readouterr().out
    assert "theft.mp4" in out and "FAIL" in out


def test_main_bad_inputs_fail(tmp_path, capsys):
    assert main(["--clips", str(tmp_path), "--detector", "fake"]) == 1  # no clips
    make_clip(tmp_path / "nolabel.mp4")
    assert main(["--clips", str(tmp_path), "--detector", "fake"]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_eval_replay_raises_dwell_alert_end_to_end(tmp_path, capsys, monkeypatch):
    zones = tmp_path / "zones.json"
    zones.write_text(
        json.dumps(
            {
                "cam1": [
                    {
                        "name": "door",
                        "polygon": [[0, 0.5], [0.5, 0.5], [0.5, 1], [0, 1]],
                        "dwell_s": 1,
                    }
                ]
            }
        )
    )
    make_clip(tmp_path / "theft.mp4", seconds=4)
    label(tmp_path / "theft.json", [{"type": "dwell", "zone": "door", "at_s": 1}])
    # feet at (17.5/64, 40/48) = inside the zone
    monkeypatch.setattr(
        "tools.eval.FakeDetector", lambda: FakeDetector([Detection(0, "person", 0.9, 5, 5, 30, 40)])
    )
    assert main(["--clips", str(tmp_path), "--detector", "fake", "--zones", str(zones)]) == 0
    out = capsys.readouterr().out
    assert "PASS" in out and "theft.mp4" in out

    assert (
        main(["--clips", str(tmp_path), "--detector", "fake", "--zones", str(tmp_path / "x")]) == 1
    )


def test_score_matches_every_primary_before_repeats():
    two = [E, {**E, "at_s": 12}]
    r = score("c", two, [alert(10.5), alert(12.5)])
    assert (r.caught, r.missed, r.repeats, r.false_alarms) == (2, 0, 0, 0)
    r = score("c", two, [alert(10.5), alert(12.5), alert(14)])
    assert (r.caught, r.repeats, r.false_alarms) == (2, 1, 0)


def test_main_fails_clip_when_behavior_engine_raises(tmp_path, capsys, monkeypatch):
    class Boom:
        def update(self, *a):
            raise KeyError("rule bug")

    monkeypatch.setattr("tools.eval.make_engine", lambda *a: Boom())
    make_clip(tmp_path / "normal.mp4")
    label(tmp_path / "normal.json", [])
    assert main(["--clips", str(tmp_path), "--detector", "fake"]) == 1
    assert "behavior engine error" in capsys.readouterr().out


def test_main_prints_zones_and_fails_without_zones_for_camera(tmp_path, capsys):
    make_clip(tmp_path / "normal.mp4")
    label(tmp_path / "normal.json", [])
    zones = tmp_path / "zones.json"
    triangle = [[0, 0], [1, 0], [1, 1]]
    zones.write_text(json.dumps({"cam1": [{"name": "porch", "polygon": triangle, "dwell_s": 1}]}))
    args = ["--clips", str(tmp_path), "--detector", "fake", "--zones", str(zones)]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert str(zones) in out and "porch" in out

    zones.write_text(json.dumps({"other": []}))
    assert main(args) == 1
    assert "no zones for camera" in capsys.readouterr().err


ZONES = [
    Zone("door", ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)), dwell_s=1.0),
    Zone("porch", ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0)), dwell_s=1.0),
]


def write_zones(path):
    triangle = [[0, 0], [1, 0], [1, 1]]
    path.write_text(
        json.dumps(
            {
                "cam1": [
                    {"name": name, "polygon": triangle, "dwell_s": 1} for name in ("door", "porch")
                ]
            }
        )
    )


def label_error(tmp_path, expected):
    make_clip(tmp_path / "clip.mp4")
    label(tmp_path / "clip.json", expected)
    with pytest.raises(LabelError) as exc:
        load_expected(tmp_path / "clip.mp4", ZONES)
    return str(exc.value)


def test_label_requires_expected_alerts_list(tmp_path):
    make_clip(tmp_path / "clip.mp4")
    (tmp_path / "clip.json").write_text(json.dumps({"notes": ""}))
    with pytest.raises(LabelError, match="expected_alerts"):
        load_expected(tmp_path / "clip.mp4", ZONES)
    for bad in ("x", 1, None, {"type": "dwell"}):
        (tmp_path / "clip.json").write_text(json.dumps({"expected_alerts": bad}))
        with pytest.raises(LabelError) as exc:
            load_expected(tmp_path / "clip.mp4", ZONES)
        message = str(exc.value)
        assert "expected_alerts" in message and "list" in message


def test_label_entry_must_be_object(tmp_path):
    for bad in ("oops", [], 3, None):
        message = label_error(tmp_path, [bad])
        assert "expected_alerts[1]" in message and "object" in message
        assert repr(bad) in message


def test_label_type_must_be_known(tmp_path):
    message = label_error(tmp_path, [{"type": "intruder", "zone": "door", "at_s": 1}])
    assert "expected_alerts[1]" in message and "type" in message and "intruder" in message
    message = label_error(tmp_path, [{"zone": "door", "at_s": 1}])
    assert "expected_alerts[1]" in message and "type" in message and "None" in message


def test_label_at_s_must_be_a_non_negative_number(tmp_path):
    for bad in (True, "1", None, -1, -0.5, float("nan"), float("inf")):
        message = label_error(tmp_path, [{"type": "dwell", "zone": "door", "at_s": bad}])
        assert "expected_alerts[1]" in message and "at_s" in message
        assert repr(bad) in message
    label(tmp_path / "clip.json", [{"type": "dwell", "zone": "door", "at_s": 0}])
    assert load_expected(tmp_path / "clip.mp4", ZONES)[0]["at_s"] == 0


def test_label_zone_must_be_known_and_case_sensitive(tmp_path):
    message = label_error(tmp_path, [{"type": "dwell", "zone": "Door", "at_s": 1}])
    assert "expected_alerts[1]" in message and "zone" in message
    assert "Door" in message and "door" in message and "porch" in message
    message = label_error(tmp_path, [{"type": "dwell", "zone": 3, "at_s": 1}])
    assert "expected_alerts[1]" in message and "zone" in message and "3" in message


def test_label_dwell_entry_requires_zone(tmp_path):
    for entry in ({"type": "dwell", "at_s": 1}, {"type": "dwell", "zone": None, "at_s": 1}):
        message = label_error(tmp_path, [entry])
        assert "expected_alerts[1]" in message and "zone" in message


def test_label_dwell_zone_needs_dwell_s(tmp_path):
    # the dwell rule skips such a zone, so the label could only ever score as "missed"
    make_clip(tmp_path / "clip.mp4")
    label(tmp_path / "clip.json", [{"type": "dwell", "zone": "yard", "at_s": 1}])
    yard = Zone("yard", ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)))
    with pytest.raises(LabelError, match="yard.*dwell_s.*door"):
        load_expected(tmp_path / "clip.mp4", [yard, *ZONES])


def test_label_error_names_entry_number_field_and_value(tmp_path):
    good = {"type": "dwell", "zone": "door", "at_s": 1}
    message = label_error(tmp_path, [good, {**good, "zone": "Door"}])
    assert "expected_alerts[2]" in message and ".zone" in message and "Door" in message


def test_main_bad_label_fails_only_that_clip(tmp_path, capsys):
    zones = tmp_path / "zones.json"
    write_zones(zones)
    make_clip(tmp_path / "bad.mp4")
    make_clip(tmp_path / "good.mp4")
    label(tmp_path / "bad.json", [{"type": "dwell", "zone": "Door", "at_s": 1}])
    label(tmp_path / "good.json", [])
    args = ["--clips", str(tmp_path), "--detector", "fake", "--zones", str(zones)]
    assert main(args) == 1
    rows = {
        line.split()[0]: line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith(("bad.mp4", "good.mp4"))
    }
    assert "FAIL" in rows["bad.mp4"] and "PASS" in rows["good.mp4"]
    assert "Door" in rows["bad.mp4"] and "door" in rows["bad.mp4"]
