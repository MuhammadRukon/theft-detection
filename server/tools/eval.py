"""Replay recorded clips through the real pipeline and score them against labels.

    uv run --frozen python -m tools.eval [--clips data/clips] [--detector yolo|fake]

Each `X.mp4` needs a label file next to it: `X.json`, else `clip.json` in the same folder:
    {"expected_alerts": [{"type": "dwell", "zone": "door", "at_s": 10}], "notes": "..."}
`at_s` is the earliest video second the alert may fire. An empty list is a "normal" clip.
Pass rules (milestone 3, decision 8): each expected alert fires within [at_s, at_s + 3];
no alert that matches nothing; at most one repeat per expected alert. Exit 1 on any failure.
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.behavior import Zone, ZonesError, load_zones, make_engine
from app.config import SERVER_DIR, Settings
from app.detection.base import Detector, FakeDetector
from app.pipeline import Pipeline
from app.sources import FileFrameSource
from app.tracking import PersonTracker

WINDOW_S = 3.0


@dataclass
class ClipResult:
    name: str
    expected: int = 0
    caught: int = 0
    missed: int = 0
    false_alarms: int = 0
    repeats: int = 0
    delays: list[float] = field(default_factory=list)
    id_switches: int = 0
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.error is None and self.missed == 0 and self.false_alarms == 0


def load_expected(mp4: Path) -> list[dict]:
    label = mp4.with_suffix(".json")
    if not label.is_file():
        label = mp4.with_name("clip.json")
    return json.loads(label.read_text())["expected_alerts"]


def score(name: str, expected: list[dict], alerts: list) -> ClipResult:
    """Match alerts (objects with type, zone, src_ts) to expected ones per the pass rules."""
    alerts = sorted(alerts, key=lambda a: a.src_ts)
    r = ClipResult(name, expected=len(expected))
    used: set[int] = set()
    for e in expected:
        mine = [
            i
            for i, a in enumerate(alerts)
            if i not in used
            and a.type == e["type"]
            and a.zone == e["zone"]
            and a.src_ts >= e["at_s"]
        ]
        first = [i for i in mine if alerts[i].src_ts <= e["at_s"] + WINDOW_S]
        if not first:
            continue
        i = first[0]
        used.add(i)
        r.caught += 1
        r.delays.append(alerts[i].src_ts - e["at_s"])
        repeat = [j for j in mine if j > i][:1]  # one repeat allowed; more count as false alarms
        used.update(repeat)
        r.repeats += len(repeat)
    r.missed = r.expected - r.caught
    r.false_alarms = len(alerts) - len(used)
    return r


def count_id_switches(events) -> int:
    """Lower-bound estimate: IDs ever seen minus the most people seen in one frame.

    Exact for a clip with a constant head count; no ground truth for identity exists.
    """
    ids = {t.track_id for e in events for t in e.tracks}
    return max(len(ids) - max((len(e.tracks) for e in events), default=0), 0)


class _ListBus:
    def __init__(self):
        self.events = []

    def publish(self, e):
        self.events.append(e)


def run_clip(
    mp4: Path, detector: Detector, cfg: Settings, zones: list[Zone] | None = None
) -> tuple[list, list]:
    """Replay one clip through Pipeline.process at the inference rate (by video time)."""
    alerts: list = []  # filled via the pipeline's on_alert seam
    bus = _ListBus()
    source = FileFrameSource(cfg.camera_id, str(mp4), loop=False, realtime=False)
    pipeline = Pipeline(
        source,
        detector,
        PersonTracker(cfg.inference_fps, cfg.track_conf),
        bus,
        cfg.camera_id,
        cfg.inference_fps,
        on_alert=alerts.append,
        engine=make_engine(cfg.camera_id, zones or []),
    )
    period, next_t, errors = 1 / cfg.inference_fps, 0.0, []

    def sink(frame):
        nonlocal next_t
        if frame.src_ts < next_t - 1e-6 or errors:
            return
        while next_t <= frame.src_ts + 1e-6:
            next_t += period
        try:
            pipeline.process(detector, frame)
        except Exception as e:
            errors.append(e)

    source.on_frame = sink
    source.start()
    source.ended.wait()
    source.stop()
    if source.error or errors:
        raise RuntimeError(source.error or errors[0])
    return alerts, bus.events


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--clips", type=Path, default=SERVER_DIR / "data" / "clips")
    ap.add_argument("--detector", choices=["fake", "yolo"], default="yolo")
    ap.add_argument("--zones", type=Path, help="zones JSON (default: the server's ZONES_PATH)")
    args = ap.parse_args(argv)
    cfg = Settings()
    try:
        zones = load_zones(args.zones or cfg.zones_path).get(cfg.camera_id, [])
    except ZonesError as e:
        print(f"zones: {e}", file=sys.stderr)
        return 1
    clips = sorted(args.clips.rglob("*.mp4"))
    if not clips:
        print(f"no *.mp4 clips in {args.clips}", file=sys.stderr)
        return 1
    if args.detector == "yolo":
        from app.detection.yolo import YoloDetector

        detector: Detector = YoloDetector(cfg)
    else:
        detector = FakeDetector()

    results = []
    for mp4 in clips:
        name = mp4.relative_to(args.clips).as_posix()
        try:
            alerts, events = run_clip(mp4, detector, cfg, zones)
            r = score(name, load_expected(mp4), alerts)
            r.id_switches = count_id_switches(events)
        except Exception as e:  # an unrunnable or unlabelled clip fails, it does not crash the run
            r = ClipResult(name, error=f"{type(e).__name__}: {e}")
        results.append(r)

    head = f"{'clip':30} {'exp':>3} {'caught':>6} {'missed':>6} {'false':>5} {'repeat':>6}"
    print(f"{head} {'delay_s':>8} {'id_sw':>5}  result")
    for r in results:
        delay = f"{sum(r.delays) / len(r.delays):.1f}" if r.delays else "-"
        verdict = "PASS" if r.passed else f"FAIL {r.error or ''}".strip()
        row = f"{r.name:30} {r.expected:>3} {r.caught:>6} {r.missed:>6} {r.false_alarms:>5}"
        print(f"{row} {r.repeats:>6} {delay:>8} {r.id_switches:>5}  {verdict}")
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
