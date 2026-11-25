from app.behavior.base import Alert, Observation, Rule, Zone
from app.behavior.dwell import DwellRule
from app.tracking import TrackedDetection


class BehaviorEngine:
    """Holds the zones and rules for one camera; owns no rule logic of its own."""

    def __init__(self, camera_id: str, zones: list[Zone], rules: list[Rule]):
        self._camera_id, self._zones, self._rules = camera_id, tuple(zones), rules

    def update(
        self,
        tracked: list[TrackedDetection],
        frame_w: int,
        frame_h: int,
        src_ts: float,
        wall_ts: float,
    ) -> list[Alert]:
        obs = Observation(self._camera_id, self._zones, tracked, frame_w, frame_h, src_ts, wall_ts)
        return [a for rule in self._rules for a in rule.update(obs)]


def make_engine(camera_id: str, zones: list[Zone]) -> BehaviorEngine:
    """The engine with the rules this build ships (fresh state each call)."""
    return BehaviorEngine(camera_id, zones, [DwellRule()])
