# Plan: record test clips and run the Milestone 3 eval

Status: **approved by the user (2026-11-27).** Not started. See [milestone 3](milestone-3.md) and [recording clips](../recording-clips.md).

## Summary

The Milestone 3 replay eval has never run because no clips exist. Add off-by-default recording of the webcam stream, record and label six dwell clips, run `server/tools/eval.py`, and write the real results into `milestone-3.md`. The work is done when the results are written down, whether the clips pass or fail.

## Context and findings

- `server/tools/eval.py:46`: the label for `X.mp4` is `X.json`, else `clip.json` in the same folder.
- `server/tools/eval.py:167`: every `.mp4` under `server/data/clips/` is scored, so raw takes must be stored elsewhere.
- `server/tools/eval.py:158-165`: the eval needs at least one zone for the camera.
- `infra/mediamtx.yml:28-29`: path `cam1` has no options. MediaMTX 1.21.4 defaults are `record: no` and `recordDeleteAfter: 1d`; the latter would delete takes.
- `dev.ps1:19`: MediaMTX starts with the repo root as working directory. The script has no parameters.
- `client/src/lib/whip.ts:8-14`: the publisher prefers H.264. The MediaMTX recording docs list no VP8 support.
- `client/src/components/CameraPreview.tsx`: "Start Camera" publishes and "Stop Camera" ends the publish, so one Start/Stop gives one file.
- `server/data/` is gitignored (`server/.gitignore:3`, checked with `git check-ignore`).
- **Approach:** the MediaMTX recorder, switched on by an environment override. Not the Windows Camera app (its output folder can sync to OneDrive, and it is a different pipeline from the live one). Not a dashboard record button (more code).
- **Reuse:** the MediaMTX recorder and `tools.eval` as it is. No new dependency.
- **Skills:** `supercharged-executor` to execute, `git-hygiene` for branch and commits (base and target are `main`), `tdd` for any bug fix, `code-review` at the end.

Sources: [MediaMTX v1.21.4 config](https://raw.githubusercontent.com/bluenviron/mediamtx/v1.21.4/mediamtx.yml), [recording docs](https://mediamtx.org/docs/features/record), [environment override discussion](https://github.com/bluenviron/mediamtx/discussions/3712).

## Constraints, assumptions, risks

Non-negotiable:

- Nobody on the agent side (executor or any subagent) opens clip frames or alert snapshots, or takes screenshots of the dashboard while the camera is on. Only file metadata and text output may be read.
- Record only consenting people. No children.
- Clips, recordings and snapshots are never committed or uploaded.
- Recording stays off unless `-Record` is passed.
- Eval results are reported as measured. Nothing is tuned only to make a clip pass.

Unverified, with mitigation:

| Item | Mitigation |
| --- | --- |
| The override `MTX_PATHS_CAM1_RECORD` works for a per-path setting | Phase 1 checks it. Fallback: a second config file, `infra/mediamtx.record.yml` |
| `FileFrameSource` replays MediaMTX fMP4 files correctly | Phase 1 checks it |
| PyAV can publish a synthetic H.264 RTSP stream for the check | If no H.264 encoder is available, use real empty-room takes from the browser instead |
| A media player may seek fMP4 poorly | Open the file in Chrome |
| Chrome may change resolution during a take | Zones are normalized; note it if a replay fails |

Limits of the result: a desk webcam says nothing about real shop cameras, and the dwell rule is not theft detection.

## Workspace setup (first step)

Branch `feature/clip-recording` from `main`, as a plain branch in the current folder. The model, `mediamtx.exe`, `zones.json` and the clips are gitignored and exist only here, so a separate worktree would lack them. This plan file is committed on that branch. Leave `docs/tasks/` untracked.

## Phase 1: recording switch

**Files**

- `infra/mediamtx.yml`, path `cam1`: `recordPath: ./server/data/recordings/%path/%Y-%m-%d_%H-%M-%S-%f`, `recordFormat: fmp4`, `recordDeleteAfter: 0s`. Recording itself stays off.
- `dev.ps1`: add a `-Record` switch. Set `MTX_PATHS_CAM1_RECORD` explicitly to `yes` or `no` before starting MediaMTX, restore the previous value in `finally`, and print `RECORDING ON` when the switch is set.
- `docs/recording-clips.md`: how to record with `-Record`, where takes land, how to move a kept take into `server/data/clips/`, and how to delete takes.
- `README.md`: mention `-Record`.

**Acceptance criteria** (use a throwaway script, not committed, that publishes 10 s of synthetic H.264 to `rtsp://127.0.0.1:8554/cam1`)

1. With `.\dev.ps1 -Record`, one publish creates exactly one new `.mp4` in `server/data/recordings/cam1/`, codec `h264`, duration 8 to 11 s.
2. With `.\dev.ps1`, the same publish creates no new file.
3. A plain run after a `-Record` run in the same PowerShell window creates no new file, and `$env:MTX_PATHS_CAM1_RECORD` has the same value as before the runs.
4. Two separate publishes create two files.
5. `RECORDING ON` is printed only with `-Record`.
6. `git status` shows no media files.
7. The user records a 10 s take of an empty room from Chrome. The file is `h264`, and a copy labelled `{"expected_alerts": []}` in `server/data/phase1-check/` gives `PASS` and exit code 0 with `uv run python -m tools.eval --clips data/phase1-check --detector fake`.
8. `uv run pytest` and `uv run ruff check` pass in `server/`.

## Phase 2: record and label (the user; the executor stops and waits)

**Steps**

1. Copy `server/config/zones.sample.json` to `server/config/zones.json`.
2. Place the webcam so a person is visible from head to feet, in steady light.
3. Adjust the `door` polygon and check it on the dashboard overlay. Restart the servers after each edit.
4. Mark the zone on the floor with tape.
5. Record one take per Start Camera / Stop Camera, 10 to 40 s each, following the dwell clip table in `docs/recording-clips.md`.
6. Watch each take, move the kept one to `server/data/clips/<name>.mp4`, and write `<name>.json` with `at_s` = second of entering the zone + 10.

**Acceptance criteria**

1. `zones.json` has zone `door` with `dwell_s` 10, and the user confirms the overlay covers the taped floor.
2. `normal-walk-through`, `normal-outside-zone` and `short-stay` have an empty `expected_alerts`.
3. `dwell-basic`, `dwell-step-out` and `two-people` each expect exactly one `dwell` in zone `door`.
4. `two-people` may be skipped if no second consenting adult is available; it is then reported as "not tested".
5. Every dwell label notes the entry second in `notes`. Every clip is 10 to 40 s long (check by metadata only).
6. All labels are written before the first eval run, and their contents are recorded in the execution progress.

## Phase 3: eval and report

**Steps**

1. Run `cd server; uv run python -m tools.eval`.
2. If a clip fails, diagnose with a throwaway text-only script (fired alert times and person count per processed frame). Save no frames.
3. Allowed changes: the zone polygon, a wrong label (state why), a clear bug (failing test first), or a threshold with a stated cause. Not allowed: changing the pass window, or tuning only to pass. Bigger problems become a separate follow-up.
4. Write the results into `docs/plans/milestone-3.md`.

**Acceptance criteria**

1. The first-run table (clip, exp, caught, missed, false, repeat, delay_s, id_sw, result) is pasted verbatim into `milestone-3.md` under a dated heading, and kept even after reruns.
2. Each `FAIL` has a one-line likely cause, or "cause unknown".
3. Each change made after the first run is listed with its reason and followed by a rerun of all clips.
4. The "NOT done" sentence about the replay eval is updated. Live step-out, stream reconnect and SSE resume stay listed as untried.

## Cross-Validation Phase

1. `uv run pytest` and `uv run ruff check` in `server/`; `bun run build` and `bun run lint` in `client/`.
2. Plain `.\dev.ps1`: the dashboard works and nothing is recorded.
3. Check every acceptance criterion above against the actual result.
4. Run `code-review` on the branch diff.
5. Confirm no media is tracked by git.
6. Ask the user whether to delete the raw takes, clips and alert snapshots.
7. Merge and push only on the user's explicit yes.

## Out of scope

Dashboard record button, zone editor, the optional clips (`bag-carry`, `fast-to-door`), other untried live checks, and Milestone 4.

Shortcut: recordings are never deleted automatically. Limit: cleanup is manual. Upgrade when recording becomes a product feature, by adding a retention setting.

## Rollback

Delete the branch, then delete `server/data/recordings/` and `server/config/zones.json` by hand.

## Execution Progress

**Status: in progress**

_Last updated: 2026-11-27. Branch: feature/clip-recording. Workspace: main working directory._

Final commit list: `5c1c86b` (recording switch)

| Phase | Status | Commit | Review | Notes |
| --- | --- | --- | --- | --- |
| 1. Recording switch | done | `5c1c86b` | deferred | general-purpose agent. AC1-8 pass. NOT run: ending dev.ps1 with Ctrl+C, Windows PowerShell 5.1, the docs' Move-Item/Remove-Item commands |
| 2. Record and label (user) | in-progress | — | deferred | — |
| 3. Eval and report | pending | — | deferred | — |
| Cross-Validation | pending | — | — | — |

### Phase 1: recording switch

Rerun by the orchestrator with synthetic H.264 published over RTSP (no camera):

- [x] AC1: one new file, `codec=h264 duration=9.93s`.
- [x] AC2: plain run, `new files: 0`.
- [x] AC3: plain run after a record run in the same process, no new file; env restored when unset, `yes` and `sentinel`.
- [x] AC4: two publishes, two files.
- [x] AC5: `RECORDING ON` only on `-Record` runs.
- [x] AC6: `git status` showed no media.
- [x] AC7: user's Chrome take is `h264`, 113.44 s, 1581 frames, resolution changed mid-take (1280x720 and 960x540), largest frame gap 0.49 s. A copy labelled `[]` gave `PASS`, exit 0 with the fake detector (sample zones); copy deleted. The user reported afterwards that the camera was covered, so this shows only that a Chrome take saves and replays; real picture content is first checked in Phase 2.
- [x] AC8: `145 passed`, ruff `All checks passed!`.
- Deviations: added `[CmdletBinding()]` to `dev.ps1` so a mistyped switch is an error.
- Known: each synthetic take holds 149 of 150 published frames.
