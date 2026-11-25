from app.sources.fps import RollingFps


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def test_steady_rate():
    c = Clock()
    f = RollingFps(window=3.0, clock=c)
    for _ in range(31):
        f.tick()
        c.t += 0.1
    assert abs(f.fps() - 10.0) < 0.01


def test_empty_and_single_tick_are_zero():
    c = Clock()
    f = RollingFps(clock=c)
    assert f.fps() == 0.0
    f.tick()
    assert f.fps() == 0.0


def test_window_evicts_and_decays_to_zero():
    c = Clock()
    f = RollingFps(window=3.0, clock=c)
    for _ in range(10):  # 10 fps burst
        f.tick()
        c.t += 0.1
    for _ in range(31):  # then 2 fps; burst must age out
        f.tick()
        c.t += 0.5
    assert abs(f.fps() - 2.0) < 0.01
    c.t += 10
    assert f.fps() == 0.0


def test_tick_alone_keeps_deque_bounded():
    c = Clock()
    f = RollingFps(window=3.0, clock=c)
    for _ in range(1000):
        f.tick()
        c.t += 0.1
    assert len(f._ticks) <= 31
