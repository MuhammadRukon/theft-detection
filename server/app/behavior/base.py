from dataclasses import dataclass
from typing import Protocol

from app.tracking import TrackedDetection


@dataclass(frozen=True)
class Alert:
    type: str
    zone: str | None  # None: the rule is not tied to a zone
    camera_id: str
    src_ts: float  # video time when the rule fired
    ts: float  # wall clock
    track_ids: tuple[int, ...]
    reason: str  # one line for a human
    score: int  # fixed 0-100 per rule


@dataclass(frozen=True)
class Zone:
    name: str
    polygon: tuple[tuple[float, float], ...]  # normalized 0-1 (x, y)
    dwell_s: float | None = None  # None: the dwell rule skips this zone


@dataclass(frozen=True)
class Observation:
    """One processed frame, handed to every rule."""

    camera_id: str
    zones: tuple[Zone, ...]
    tracked: list[TrackedDetection]
    frame_w: int
    frame_h: int
    src_ts: float  # video time; rules must use this, never the wall clock
    wall_ts: float


class Rule(Protocol):
    """A rule owns its own state and is called once per frame, in video-time order."""

    def update(self, obs: Observation) -> list[Alert]: ...
