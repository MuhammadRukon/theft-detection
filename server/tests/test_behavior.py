import json

import pytest

from app.behavior import (
    BehaviorEngine,
    DwellRule,
    Zone,
    ZonesError,
    load_zones,
    make_engine,
    point_in_polygon,
)
from app.tracking import TrackedDetection

SQUARE = ((0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8))
W, H = 100, 100


def person(tid, cx=50, bottom=50, class_name="person"):
    return TrackedDetection(tid, 0, class_name, 0.9, cx - 5, bottom - 20, cx + 5, bottom)


def engine(dwell_s=10.0, **kw):
    return BehaviorEngine("cam1", [Zone("door", SQUARE, dwell_s)], [DwellRule(**kw)])


def step(e, t, *people):
    return e.update(list(people), W, H, t, 1000 + t)


def test_point_in_polygon():
    assert point_in_polygon(0.5, 0.5, SQUARE)
    assert not point_in_polygon(0.1, 0.5, SQUARE)
    assert not point_in_polygon(0.5, 0.9, SQUARE)
    assert point_in_polygon(0.2, 0.5, SQUARE)  # on an edge
    assert point_in_polygon(0.2, 0.2, SQUARE)  # on a vertex
    assert not point_in_polygon(0.9, 0.2, SQUARE)  # level with an edge, outside
    concave = ((0, 0), (1, 0), (1, 1), (0.5, 0.4), (0, 1))
    assert point_in_polygon(0.1, 0.5, concave) and not point_in_polygon(0.5, 0.8, concave)


def write(tmp_path, data):
    p = tmp_path / "zones.json"
    p.write_text(data if isinstance(data, str) else json.dumps(data))
    return p


def zone(**kw):
    return {"name": "door", "polygon": [[0, 0], [1, 0], [1, 1]], "dwell_s": 10, **kw}


def test_load_zones_ok(tmp_path):
    z = load_zones(write(tmp_path, {"cam1": [zone()], "cam2": []}))
    assert (
        z["cam1"] == [Zone("door", ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)), 10.0)] and z["cam2"] == []
    )


def test_load_zones_without_dwell_s(tmp_path):
    raw = zone()
    del raw["dwell_s"]
    (z,) = load_zones(write(tmp_path, {"cam1": [raw]}))["cam1"]
    assert z.dwell_s is None


@pytest.mark.parametrize(
    "data, msg",
    [
        ("{nope", "not valid JSON"),
        ([], "object of camera_id"),
        ({"cam1": {}}, "must be a list"),
        ({"cam1": [zone(polygon=[[0, 0], [1, 1]])]}, "at least 3 points"),
        ({"cam1": [zone(polygon=[[0, 0], [1, 1], [2, 0]])]}, "in 0-1"),
        ({"cam1": [zone(polygon=[[0, 0], [1, 1], [-0.1, 0]])]}, "in 0-1"),
        ({"cam1": [zone(polygon=[[0, 0], [1, 1], [0.5]])]}, "[x, y]"),
        ({"cam1": [zone(dwell_s=0)]}, "dwell_s"),
        ({"cam1": [zone(dwell_s="5")]}, "dwell_s"),
        ({"cam1": [zone(dwell_s=-1)]}, "dwell_s"),
        ({"cam1": [zone(dwell_s=None)]}, "dwell_s"),
        ({"cam1": [zone(name="")]}, "name"),
        ({"cam1": [zone(), zone()]}, "duplicate zone name 'door'"),
    ],
)
def test_load_zones_errors(tmp_path, data, msg):
    with pytest.raises(ZonesError, match=msg):
        load_zones(write(tmp_path, data))


def test_load_zones_missing_file(tmp_path):
    with pytest.raises(ZonesError, match="cannot read"):
        load_zones(tmp_path / "none.json")


def test_sample_zones_file_is_valid():
    from app.config import SERVER_DIR

    assert load_zones(SERVER_DIR / "config" / "zones.sample.json")["cam1"]


def test_engine_empty_input():
    assert step(engine(), 0.0) == []


def test_dwell_fires_once_with_alert_fields():
    e = engine(10)
    fired = [(t, step(e, t, person(4))) for t in range(0, 12)]
    got = [(t, a) for t, a in fired if a]
    assert [t for t, _ in got] == [10]
    (a,) = got[0][1]
    assert (a.type, a.zone, a.camera_id, a.src_ts, a.ts) == ("dwell", "door", "cam1", 10, 1010)
    assert a.track_ids == (4,) and a.score == 60
    assert a.reason == "person #4 stayed in zone 'door' for 10 s"


def test_uses_source_time_not_call_count():
    e = engine(10)
    for t in (0.0, 2.0, 4.0, 6.0, 8.0, 9.9):  # six calls span nearly 10 s of video
        assert step(e, t, person(1)) == []
    assert len(step(e, 10.0, person(1))) == 1


def test_grace_keeps_timer_and_longer_gap_resets():
    e = engine(10)
    for t in (0.0, 2.0, 4.0, 6.0, 8.0):
        step(e, t, person(1))
    # unseen at 9; back at 10 = exactly 2 s since last seen: timer kept, 10 s since entry
    assert len(step(e, 10.0, person(1))) == 1

    e = engine(10)
    step(e, 0.0, person(1))
    step(e, 4.0, person(1))
    step(e, 6.5, person(1))  # 2.5 s unseen: reset, timer restarts at 6.5
    got = [a for t in (8.0, 10.0, 12.0, 14.0, 16.0, 16.5) for a in step(e, t, person(1))]
    assert [a.src_ts for a in got] == [16.5]


def alerts_at(e, *spans):
    """Alert times for one person over (from_s, to_s, where) spans, one frame per second."""
    people = {"in": [person(1)], "out": [person(1, cx=95)], "unseen": []}
    return [
        a.src_ts
        for start, end, where in spans
        for t in range(start, end)
        for a in step(e, float(t), *people[where])
    ]


def test_stepping_out_for_1s_keeps_timer():
    # frames at 5 fps: inside, outside from 5.0 to 5.8, back at 6.0
    e = engine(10)
    got = [
        a.src_ts
        for i in range(0, 56)
        for a in step(e, i / 5, person(1, cx=95 if 25 <= i < 30 else 50))
    ]
    assert got == [10.0]


@pytest.mark.parametrize("away", ["out", "unseen"])
def test_one_frame_away_keeps_timer(away):
    assert alerts_at(engine(10), (0, 5, "in"), (5, 6, away), (6, 15, "in")) == [10]


@pytest.mark.parametrize("away", ["out", "unseen"])
def test_away_for_2_5s_resets_timer(away):
    e = engine(10)
    alerts_at(e, (0, 5, "in"))  # last inside at 4
    other = [person(1, cx=95)] if away == "out" else []
    assert step(e, 5.0, *other) == [] and step(e, 6.5, *other) == []
    assert alerts_at(e, (7, 25, "in")) == [17]


def test_dwell_reached_while_outside_fires_on_return():
    assert alerts_at(engine(10), (0, 10, "in"), (10, 11, "out"), (11, 15, "in")) == [11]


def test_one_alert_per_visit_however_long():
    assert alerts_at(engine(10), (0, 101, "in")) == [10]


@pytest.mark.parametrize("away", ["out", "unseen"])
def test_new_visit_after_leaving_gets_second_alert(away):
    got = alerts_at(engine(10), (0, 15, "in"), (15, 18, away), (18, 40, "in"))
    assert got == [10, 28]


@pytest.mark.parametrize("away", ["out", "unseen"])
def test_brief_absence_after_firing_does_not_realert(away):
    # last inside at 14, back at 16: exactly the 2 s grace, still the same visit
    assert alerts_at(engine(10), (0, 15, "in"), (15, 16, away), (16, 60, "in")) == [10]


def test_bottom_centre_decides_not_box_centre():
    e = engine(1)
    low = person(1, bottom=90)  # box overlaps the zone but its feet are below it
    step(e, 0.0, low)
    assert step(e, 5.0, low) == []


def test_tracks_are_independent_and_non_persons_ignored():
    e = engine(10)
    step(e, 0.0, person(1), person(9, class_name="car"))
    step(e, 6.0, person(2), person(9, class_name="car"))  # 1 unseen 6 s: reset; 2 starts now
    step(e, 7.0, person(1), person(2))
    got = [a for t in range(8, 20) for a in step(e, float(t), person(1), person(2))]
    assert [(a.src_ts, a.track_ids) for a in got] == [(16, (2,)), (17, (1,))]


def test_dwell_ignores_zone_without_dwell_s():
    e = make_engine("cam1", [Zone("plain", SQUARE), Zone("door", SQUARE, 1)])
    step(e, 0.0, person(1))
    assert [a.zone for a in step(e, 60.0, person(1)) + step(e, 61.0, person(1))] == ["door"]


def test_make_engine_has_dwell():
    e = make_engine("cam1", [Zone("door", SQUARE, 1)])
    step(e, 0.0, person(1))
    assert len(step(e, 1.0, person(1))) == 1
