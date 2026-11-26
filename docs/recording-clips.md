# Recording and labelling test clips

> **Draft.** The label format is implemented by `server/tools/eval.py`. If that file disagrees with this guide, the file wins and this guide must be updated.

Clips are replayed through the real pipeline (detector, tracker, rules) to measure how many expected alerts fire, how many false alarms appear, and how late alerts are. Without realistic clips we can only guess at thresholds. A desk webcam in dim light is a poor stand-in for a shop camera.

## Consent and privacy

- Record only people who agreed to be filmed, and tell them what the clips are for.
- Clips stay on this machine in `server/data/clips/`. That folder is gitignored. Never commit, push or upload clips.
- Nothing in this project recognises faces. Do not add any.
- Delete clips when you no longer need them.

## Camera setup

- Fixed camera position. No zooming or moving during a clip.
- Landscape, 1280x720 or 960x540, about 15 fps. Save as `.mp4`.
- Decent, steady light. Earlier tests in dim light gave flickery detection.
- Keep people head to toe in view where you can. The dwell rule uses the bottom-centre of the person box, roughly the feet, so feet must be visible and the zone must be where feet actually stand.
- Each clip 10-40 s. Start with the scene empty for 1-2 s.

## The zone

Alerts need a zone. Zones live in `server/config/zones.json` (copy `server/config/zones.sample.json`): polygons in normalized 0-1 coordinates of the frame, plus `dwell_s` in seconds. `dwell_s` has no default: it is optional per zone but required for dwell alerts, so a zone without it raises none (the sample sets 10). Put the zone on the floor area where you will stand. Keep the same zone file for every clip from the same camera position.

## Suggested clips

The dwell rule raises one alert per visit. A visit ends only when the person has not been seen inside the zone for more than 2 s (outside it, or undetected); after that, a new full `dwell_s` stay raises a new alert.

Only the first group exercises the one rule that exists today (dwell). The second group is for later rules; record them if convenient.

**Dwell rule (needed)**

| Clip | What happens | Expected alert |
| --- | --- | --- |
| `normal-walk-through` | Person walks across the scene, through the zone without stopping | none |
| `normal-outside-zone` | Person stands still outside the zone for 20 s or more | none |
| `dwell-basic` | Person walks in and stands in the zone for longer than `dwell_s` | one `dwell` |
| `dwell-step-out` | Person stands in the zone, steps out for about 1 s before `dwell_s` is up, steps back and stays | one `dwell`, `dwell_s` after first entering (the timer keeps running during an absence of up to 2 s) |
| `short-stay` | Person stands in the zone for less than `dwell_s`, then leaves | none |
| `two-people` | Two people in the scene; one stands in the zone past `dwell_s`, the other walks past | one `dwell` |

**Later rules (optional)**

| Clip | What happens | Expected alert |
| --- | --- | --- |
| `bag-carry` | Person carries a bag through the scene | none for now (objects are not detected yet) |
| `fast-to-door` | Two people move quickly toward a door area | none for now (no rush rule yet) |

## Label files

Each clip needs a JSON label file with the same base name next to it: `dwell-basic.mp4` and `dwell-basic.json` (if that file is absent, `clip.json` in the same folder is used).

```json
{
  "expected_alerts": [{"type": "dwell", "zone": "door", "at_s": 14}],
  "notes": "Person enters at 3 s and stands in the zone until the end."
}
```

A normal clip has an empty list:

```json
{
  "expected_alerts": [],
  "notes": "Person walks across without stopping."
}
```

- `type` is `dwell` for now.
- `zone` is the zone name in your zones file. Omit it (or use `null`) only for an alert that has no zone; `dwell` alerts always have one.
- `at_s` is video time in seconds from the start of the clip. It is the earliest second the alert may fire: the moment the person has been inside the zone for `dwell_s`. Example: they step into the zone at 4 s and `dwell_s` is 10, so `at_s` is 14.
- A clip passes when each expected alert fires between `at_s` and `at_s + 3` seconds, and no other alert fires, except that at most one repeat per expected alert is tolerated.

## Run the evaluation

Put the clips and labels in `server/data/clips/`, then:

```powershell
cd server; uv run python -m tools.eval
```

It prints, per clip, alerts caught, missed, false alarms, alert delay and track-ID switches, and exits non-zero if any clip fails. Report misses honestly; do not tune thresholds just to make a clip pass.
