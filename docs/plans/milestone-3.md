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
4. **First rule: dwell.** A person track stays inside a marked zone longer than N seconds (set per zone as `dwell_s`, no default; the sample file uses 10 s; changed after review, 2026-11-26). The "group rushing a door" rule is second, as another plugin of the same framework. Rules live in a new `behavior/` module as plain functions of track history, run inline in the pipeline thread right after the tracker so detection stays independent of rule code.
5. **Zones:** JSON polygons in normalized 0-1 coordinates, per camera (`server/config/zones.json`, with a committed sample). The dashboard draws zones read-only over the video. No zone editor yet.
6. **Alert:** fields `alert_id`, `camera_id`, `type` ("dwell"), `score` (fixed 0-100 per rule), `reason` (one line, e.g. "person #4 stayed in zone 'door' for 12 s"), `track_ids`, `ts`, `evidence_url`. One alert per visit: after firing for a (zone, track), no further alert while the visit continues; a new alert needs the visit to end (decision 10) and then a new full `dwell_s` stay. This replaces the earlier per-(track, rule) cooldown (changed after review, 2026-11-26). Evidence is one JPEG of the triggering frame with boxes and the zone drawn, saved with `alert.json` by the file-based `AlertStore` under a gitignored folder. SSE `alert` event carries an `id:` so the browser resumes after a reconnect; snapshot served at `GET /api/alerts/{id}/snapshot.jpg`. Dashboard shows a newest-first list with thumbnails. No acknowledge or resolve button yet.
7. **Time base:** rules use the video's own source timestamps, not the wall clock, so a clip replays to the same alerts at any speed. Frames carry both a source timestamp and the wall-clock one (still used for latency).
8. **Pass rules (eval):** per clip, every expected alert fires between the dwell threshold and the threshold plus 3 s; no alert on "normal" clips; at most one repeat alert per expected one. The report prints caught, missed, false alarms and alert delay per clip.
9. **Replay and eval:** `FileFrameSource` gains non-looping and as-fast-as-possible modes, keeping source timestamps. `server/tools/eval.py` runs each clip through the real detector, tracker and rules (the same pipeline code, not a copy), subsamples frames to the inference rate by video time, reads expected alerts from `clip.json` next to each mp4, prints a table, and exits non-zero on failure. Clips and labels live in gitignored `server/data/clips/`.
10. **Dwell semantics:** a person is in a zone when the bottom-centre of their box is inside the polygon. Time accumulates per track ID. A visit continues while the track was last seen inside the zone at most 2 s of video time ago, whether it has since gone undetected or been seen outside (including box jitter at the edge): the timer keeps running. Beyond 2 s the visit ends and the timer resets (changed after review, 2026-11-26). Track-ID switches (seen on the real webcam) are NOT special-cased; the eval reports how often they happen, and a smarter fix waits for a later milestone if it matters.

## Phases

Each phase is its own session and branch. Phases 2 and 3 run in parallel after phase 1; phase 4 after 3 (and needs the zone config shape from 2); phase 5 needs the user's clips.

1. **Time base and replay.** Frames carry source timestamps; `FileFrameSource` non-looping and fast modes; `server/tools/eval.py` with clip and label loading, subsampling, report and exit code, no rules yet (reports zero alerts). Tests with a generated synthetic clip.
2. **Zones, dwell rule, behavior engine.** `behavior/` module: zone loading and validation, point-in-polygon, dwell rule with 2 s grace, rule plugin interface, cooldown (cooldown replaced by one alert per visit after review, 2026-11-26). Runs inline after the tracker in the pipeline. Pure unit tests on fake track histories and a fake clock. Alert objects produced in memory only (no storage yet).
3. **Alert model, store, API.** `AlertEvent` schema, file-based `AlertStore` (alert.json plus annotated snapshot), SSE `alert` event with `id:`/`Last-Event-ID`, snapshot endpoint, retention setting, gitignored data folder. Tests with fake alerts.
4. **Dashboard.** TS types, zones drawn read-only over the video, alert list with thumbnails, resume after reconnect.
5. **Eval, tuning, real run, review.** Run `eval.py` on the user's clips, report results honestly, tune only thresholds, real-webcam check, update docs, cross-validation pass.

## Out of scope

Object detection and association (Milestone 4), "left alone" objects, rush/loitering-count rules beyond dwell, zone editor, acknowledge/resolve, risk scoring beyond a fixed per-rule score, ID-switch repair, custom model training, ONNX/GPU, multi-camera registry, auth, database.

## Status (2026-11-26)

Phases 1-4, integration and review fixes are in; 145 server tests pass. Live webcam run: zone, boxes and dwell alerts worked.

**Replay eval:** run on 2026-11-28, results below. The Done-when pass rules are **not met**: both dwell clips fail. Still not tried live: stepping out under 2 s, stream reconnect, SSE resume. Merged to main at the user's request.

## Replay eval, first run (2026-11-28, code at 3a94d22, yolo)

```
clip                           exp caught missed false repeat  delay_s id_sw  result
dwell-basic.mp4                  1      0      1     1      0        -     0  FAIL
dwell-step-out.mp4               1      0      1     1      0        -     0  FAIL
normal-outside-zone.mp4          0      0      0     0      0        -     0  PASS
normal-walk-through.mp4          0      0      0     0      0        -     2  PASS
short-stay.mp4                   0      0      0     0      0        -     0  PASS
```

Nothing was changed after this run (no code, zone, threshold or label), so there is no rerun.

Each `FAIL` still raised one alert, outside its label's window. Both alerts fired 10 s after the detector first saw the person inside the zone for that visit. Timings below come from a text-only script (alert times, and per 0.2 s sample whether the box bottom-centre was in the zone); no frames were viewed or saved.

- `dwell-basic`: likely cause is label precision. The alert fired at 23.4 s; the label allows 24 to 27 s. The label came from reading a player clock in whole seconds (reported "0:14 / 0:16"), the detector saw entry at about 13.4 s, and the pass window has no early slack.
- `dwell-step-out`: likely cause is that the take did not contain the scenario. The person was out of the zone for about 3 s (about 18.6 to 21.6 s), over the 2 s grace, so the timer restarted and the alert fired at 31.6 s. The label expected the timer to keep running (alert from 20 s). The brief-absence behaviour is therefore still untested on video.

What each `PASS` covered:

- `normal-outside-zone`: person never counted as inside the zone.
- `short-stay`: inside for about 7.6 s, under the 10 s threshold.
- `normal-walk-through`: inside only briefly, in two short passes. 2 ID switches: the person was not detected for about 3 s (likely out of frame) and came back under a new ID, and a second box appeared intermittently near the middle of the picture.

Limits:

- `two-people` was not tested (no second consenting adult available).
- One person, one small room, one desk webcam. This says nothing about real shop cameras, and the dwell rule is not theft detection.
- A second "person" box appears now and then at about the same place (feet x near 0.5) in several clips. No second person was available during recording, so it is probably a false detection; not confirmed, as no frames were viewed.
- `dwell-basic` and `normal-outside-zone` are the first 39.9 s of longer takes. A per-second detection check was run on the `dwell-basic` take before its label was written; the label itself came from the user's own viewing.

Possible follow-ups (not done): label entry times more finely or revisit the early edge of the pass window; record a new step-out take with an absence under 2 s; look into the intermittent second box.
