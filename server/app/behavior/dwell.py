from app.behavior.base import Alert, Observation
from app.behavior.zones import point_in_polygon

SCORE = 60


class DwellRule:
    """A person whose box bottom-centre stays in a zone for the zone's dwell_s raises one alert.

    A visit lasts while the (zone, track) was last seen in the zone at most `grace_s` ago (video
    time). A shorter absence, whether undetected or seen outside (box jitter at the edge), keeps
    the timer running; a longer one ends the visit. Each visit raises at most one alert, so
    another needs a new visit and a full dwell_s again. Track-ID switches are not repaired: a
    new ID starts at zero.
    """

    def __init__(self, grace_s: float = 2.0):
        self._grace = grace_s
        self._since: dict[tuple[str, int], float] = {}  # (zone, track) -> entered at
        self._last_in: dict[tuple[str, int], float] = {}
        self._fired: set[tuple[str, int]] = set()

    def update(self, obs: Observation) -> list[Alert]:
        now = obs.src_ts
        for key in [k for k, t in self._last_in.items() if now - t > self._grace]:
            del self._since[key], self._last_in[key]
            self._fired.discard(key)
        alerts = []
        people = [t for t in obs.tracked if t.class_name == "person"]
        for zone in obs.zones:
            if zone.dwell_s is None:
                continue
            for t in people:
                key = (zone.name, t.track_id)
                x, y = (t.x1 + t.x2) / 2 / obs.frame_w, t.y2 / obs.frame_h
                if not point_in_polygon(x, y, zone.polygon):
                    continue
                self._since.setdefault(key, now)
                self._last_in[key] = now
                stayed = now - self._since[key]
                if stayed >= zone.dwell_s and key not in self._fired:
                    self._fired.add(key)
                    reason = f"person #{t.track_id} stayed in zone '{zone.name}' for {stayed:.0f} s"
                    alerts.append(
                        Alert(
                            type="dwell",
                            zone=zone.name,
                            camera_id=obs.camera_id,
                            src_ts=now,
                            ts=obs.wall_ts,
                            track_ids=(t.track_id,),
                            reason=reason,
                            score=SCORE,
                        )
                    )
        return alerts
