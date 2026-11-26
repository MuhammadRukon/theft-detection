from app.detection.base import Detection
from app.tracking import PersonTracker


def box(x, y=100, conf=0.9):
    return Detection(0, "person", conf, x, y, x + 50, y + 120)


def run(tracker, frames):
    return [tracker.update(f) for f in frames]


def test_moving_box_keeps_one_id():
    t = PersonTracker(5.0)
    outs = run(t, [[box(100 + 4 * i)] for i in range(10)])
    ids = {o[0].track_id for o in outs if o}
    assert len(ids) == 1
    assert outs[-1] and outs[-1][0].class_name == "person"


def test_two_separated_boxes_two_ids():
    t = PersonTracker(5.0)
    outs = run(t, [[box(100), box(500)] for _ in range(4)])
    assert len({d.track_id for d in outs[-1]}) == 2


def test_empty_update_returns_empty():
    t = PersonTracker(5.0)
    assert t.update([]) == []
    run(t, [[box(100)]] * 3)
    assert t.update([]) == []


def test_id_survives_short_gap():
    t = PersonTracker(5.0)
    outs = run(t, [[box(100)]] * 4)
    tid = outs[-1][0].track_id
    run(t, [[], []])
    back = t.update([box(104)])
    assert back and back[0].track_id == tid


def test_track_id_is_plain_int():
    t = PersonTracker(5.0)
    out = run(t, [[box(100)]] * 3)[-1]
    assert type(out[0].track_id) is int


def test_low_conf_detection_keeps_confirmed_track():
    # ByteTrack's second stage matches weak boxes (conf below min_conf) to existing tracks
    t = PersonTracker(5.0, 0.4)
    tid = run(t, [[box(100)]] * 4)[-1][0].track_id
    out = t.update([box(100, conf=0.3)])
    assert [d.track_id for d in out] == [tid]


def test_id_survives_two_second_gap():
    # 10 missed frames at 5 fps: the dwell rule's 2 s grace needs the same ID back
    t = PersonTracker(5.0)
    tid = run(t, [[box(100)]] * 4)[-1][0].track_id
    run(t, [[]] * 10)
    back = t.update([box(100)])
    assert back and back[0].track_id == tid
