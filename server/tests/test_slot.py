import numpy as np

from app.sources.base import Frame, LatestSlot


def frame(pts):
    return Frame("cam1", 0.0, pts, 2, 2, np.zeros((2, 2, 3), np.uint8))


def test_empty():
    assert LatestSlot().get() is None


def test_unread_frame_is_replaced_and_counted():
    s = LatestSlot()
    s.put(frame(1))
    s.put(frame(2))
    s.put(frame(3))
    assert s.dropped == 2
    assert s.get().pts == 3


def test_read_frame_is_not_a_drop():
    s = LatestSlot()
    s.put(frame(1))
    s.get()
    s.put(frame(2))
    assert s.dropped == 0
    assert s.get().pts == 2
