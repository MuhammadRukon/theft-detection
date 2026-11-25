from app.metrics import RollingStats


def test_empty_is_none():
    s = RollingStats()
    assert s.p50() is s.p95() is s.mean() is None


def test_single_value():
    s = RollingStats()
    s.add(7.0)
    assert s.p50() == s.p95() == s.mean() == 7.0


def test_nearest_rank():
    s = RollingStats()
    for v in range(1, 101):
        s.add(float(v))
    assert (s.p50(), s.p95(), s.mean()) == (50.0, 95.0, 50.5)


def test_window_evicts_oldest():
    s = RollingStats(window=3)
    for v in (100, 1, 2, 3):
        s.add(float(v))
    assert s.p95() == 3.0 and s.mean() == 2.0
