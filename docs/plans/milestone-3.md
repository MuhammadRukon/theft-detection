# Milestone 3: first end-to-end rule slice (dwell alert with evidence)

Status: **approved by the user (2026-11-26) after grilling.** Earlier drafts proposed object detection first; that was replaced (see Decisions). Builds on Milestone 2 (branch `feature/person-detection`). See [architecture](../architecture.md) and [milestone 2](milestone-2.md).

**Goal:** prove the whole path from camera to human reviewer with one simple, honest rule and no new model: a person stays in a marked zone longer than N seconds, the system raises an alert with a snapshot, the dashboard lists it. Plus a repeatable way to test it on recorded clips.

**Done when:**
- Replaying the user's recorded clips through the real pipeline gives the expected alerts and no false alerts on "normal" clips (pass rules below), reported by `server/tools/eval.py`.
- Live webcam: standing in a configured zone longer than the threshold raises one alert, with a snapshot, visible in the dashboard list; trigger-to-dashboard under 1 s on the server side.
- Misses are reported with measured numbers, not tuned away.

## Decisions (grilled and confirmed)

1. **Direction:** Milestone 3 is one end-to-end rule slice (rule, alert event, evidence snapshot, dashboard list). Object detection (bags, knife, bat) and object-to-person association move to Milestone 4, once there is footage to judge them on.
2. **Test footage:** the user records 5-10 short staged clips with consenting people (walking through, loitering in a zone, two people moving fast, someone with a bag) and writes a small label file per clip. Clips replay through `FileFrameSource`.
3. **Footage and snapshot handling:** clips and snapshots are only on this machine, in gitignored folders, never committed or uploaded; snapshot retention is a setting (delete after N days). No face recognition or biometric storage.
4. **First rule: dwell.** A person track stays inside a marked zone longer than N seconds (default 10 s, configurable per zone). The "group rushing a door" rule is second, as another plugin of the same framework. Rules live in a new `behavior/` module as plain functions of track history, run inline in the pipeline thread right after the tracker so detection stays independent of rule code.
5. **Zones:** JSON polygons in normalized 0-1 coordinates, per camera (`server/config/zones.json`, with a committed sample). The dashboard draws zones read-only over the video. No zone editor yet.
6. **Alert:** fields `alert_id`, `camera_id`, `type` ("dwell"), `score` (fixed 0-100 per rule), `reason` (one line, e.g. "person #4 stayed in zone 'door' for 12 s"), `track_ids`, `ts`, `evidence_url`. A cooldown per (track, rule) stops repeats. Evidence is one JPEG of the triggering frame with boxes and the zone drawn, saved with `alert.json` by the file-based `AlertStore` under a gitignored folder. SSE `alert` event carries an `id:` so the browser resumes after a reconnect; snapshot served at `GET /api/alerts/{id}/snapshot.jpg`. Dashboard shows a newest-first list with thumbnails. No acknowledge or resolve button yet.
7. **Time base:** rules use the video's own source timestamps, not the wall clock, so a clip replays to the same alerts at any speed. Frames carry both a source timestamp and the wall-clock one (still used for latency).
8. **Pass rules (eval):** per clip, every expected alert fires between the dwell threshold and the threshold plus 3 s; no alert on "normal" clips; at most one repeat alert per expected one. The report prints caught, missed, false alarms and alert delay per clip.
9. **Replay and eval:** `FileFrameSource` gains non-looping and as-fast-as-possible modes, keeping source timestamps. `server/tools/eval.py` runs each clip through the real detector, tracker and rules (the same pipeline code, not a copy), subsamples frames to the inference rate by video time, reads expected alerts from `clip.json` next to each mp4, prints a table, and exits non-zero on failure. Clips and labels live in gitignored `server/data/clips/`.
10. **Dwell semantics:** a person is in a zone when the bottom-centre of their box is inside the polygon. Time accumulates per track ID. A track gone for up to 2 s keeps its timer; after that it resets. Track-ID switches (seen on the real webcam) are NOT special-cased; the eval reports how often they happen, and a smarter fix waits for a later milestone if it matters.

## Phases

Each phase is its own session and branch. Phases 2 and 3 run in parallel after phase 1; phase 4 after 3 (and needs the zone config shape from 2); phase 5 needs the user's clips.

1. **Time base and replay.** Frames carry source timestamps; `FileFrameSource` non-looping and fast modes; `server/tools/eval.py` with clip and label loading, subsampling, report and exit code, no rules yet (reports zero alerts). Tests with a generated synthetic clip.
2. **Zones, dwell rule, behavior engine.** `behavior/` module: zone loading and validation, point-in-polygon, dwell rule with 2 s grace, rule plugin interface, cooldown. Runs inline after the tracker in the pipeline. Pure unit tests on fake track histories and a fake clock. Alert objects produced in memory only (no storage yet).
3. **Alert model, store, API.** `AlertEvent` schema, file-based `AlertStore` (alert.json plus annotated snapshot), SSE `alert` event with `id:`/`Last-Event-ID`, snapshot endpoint, retention setting, gitignored data folder. Tests with fake alerts.
4. **Dashboard.** TS types, zones drawn read-only over the video, alert list with thumbnails, resume after reconnect.
5. **Eval, tuning, real run, review.** Run `eval.py` on the user's clips, report results honestly, tune only thresholds, real-webcam check, update docs, cross-validation pass.

## Out of scope

Object detection and association (Milestone 4), "left alone" objects, rush/loitering-count rules beyond dwell, zone editor, acknowledge/resolve, risk scoring beyond a fixed per-rule score, ID-switch repair, custom model training, ONNX/GPU, multi-camera registry, auth, database.
