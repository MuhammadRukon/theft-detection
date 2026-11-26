from app.behavior.base import Alert, Observation
from app.behavior.zones import point_in_polygon

SCORE = 60


class DwellRule:
    """A person whose box bottom-centre stays in a zone for the zone's dwell_s raises one alert.

    A track not seen in the zone for up to `grace_s` keeps its timer (the gap counts as time
    spent); longer, or seen outside the zone, resets it. After firing, the same (zone, track)
    stays quiet for `cooldown_s`. Track-ID switches are not repaired: a new ID starts at zero.
    """

    def __init__(self, grace_s: float = 2.0, cooldown_s: float = 30.0):
        self._grace, self._cooldown = grace_s, cooldown_s
        self._since: dict[tuple[str, int], float] = {}  # (zone, track) -> entered at
        self._last_in: dict[tuple[str, int], float] = {}
        self._fired: dict[tuple[str, int], float] = {}

    def update(self, obs: Observation) -> list[Alert]:
        now = obs.src_ts
        for key in [k for k, t in self._last_in.items() if now - t > self._grace]:
            del self._since[key], self._last_in[key]
        for key in [k for k, t in self._fired.items() if now - t >= self._cooldown]:
            del self._fired[key]
        alerts = []
        people = [t for t in obs.tracked if t.class_name == "person"]
        for zone in obs.zones:
            if zone.dwell_s is None:
                continue
            for t in people:
                key = (zone.name, t.track_id)
                x, y = (t.x1 + t.x2) / 2 / obs.frame_w, t.y2 / obs.frame_h
                if not point_in_polygon(x, y, zone.polygon):
                    self._since.pop(key, None)
                    self._last_in.pop(key, None)
                    continue
                self._since.setdefault(key, now)
                self._last_in[key] = now
                stayed = now - self._since[key]
                if stayed >= zone.dwell_s and key not in self._fired:
                    self._fired[key] = now
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
