# Milestone 1: webcam into Python, measure incoming FPS

Scope: no YOLO. See [architecture](../architecture.md).

**Done when:** the dashboard shows incoming FPS and resolution, measured in Python from the real webcam.

## Steps

Each step is verifiable on its own.

### 1. MediaMTX

- Create `infra/mediamtx.yml`: WebRTC (WHIP/WHEP) and RTSP enabled, bound to `127.0.0.1`.
- Download the MediaMTX Windows binary (ask the user first: name file, source, size).
- Verify: publish and play from MediaMTX's built-in test page.

### 2. React publish and view

- Reuse `client/src/components/CameraPreview.tsx` camera start/stop.
- Add a hand-written WHIP client (`RTCPeerConnection`, offer, `fetch` POST SDP, apply answer). Request 1280x720 @ 15 via `getUserMedia` constraints. Prefer H.264 with VP8 fallback.
- Add a WHEP viewer playing the stream back from MediaMTX.
- Verify: webcam goes browser -> MediaMTX -> browser.

### 3. Python frame sources and stats

- `server/` with `uv`, `ruff`, `pytest`; FastAPI app in `app/main.py`.
- `FrameSource` interface. `RtspFrameSource` uses PyAV with `rtsp_transport=tcp`, `fflags=nobuffer`, `flags=low_delay`, reader thread, latest-frame slot. `FileFrameSource` loops an mp4.
- Rolling FPS counter, resolution, decode time, dropped-frame count.
- Tests: FPS counter and latest-frame slot against `FileFrameSource`.
- Verify: run server against MediaMTX stream, stats print to log.

### 4. SSE stats to dashboard

- `GET /api/events` emits `stats` once per second. Vite proxy forwards `/api`.
- Hand-written TS event types in `client/src/types/`.
- Dashboard shows FPS and resolution next to the video.
- `dev.ps1` at repo root starts MediaMTX, `uvicorn --reload`, and `vite`.

## Out of scope

Detection, tracking, behavior rules, alerts, evidence store, auth, phone camera, GPU.

## Execution Progress

**Status: COMPLETE except real-webcam check, ready for PR**

_Last updated: 2026-11-26 — Branch: feature/webcam-fps-ingest — Workspace: main working directory_

Final commit list: `e8d3d00` (init), `9f80481` (baseline)

| Phase | Status | Commit | Review | Notes |
| --- | --- | --- | --- | --- |
| 1. MediaMTX | done | `804502b` | deferred | v1.21.4 binary (28.8 MB) downloaded to gitignored infra/bin. NOT run: real publish/ICE over loopback-only config (needs browser, phase 2); no checksum check |
| 2. React publish and view | done | see git log | deferred | build + lint pass; page loads vs live MediaMTX, WHEP 404 path OK. NOT run: real webcam publish, H.264 negotiation, WHEP playback, Stop/DELETE. Viewer does not detect remote hangup |
| 3. Python sources and stats | done | see git log | deferred | ruff + 7 pytest pass; e2e: PyAV H.264 publisher -> MediaMTX -> RtspFrameSource measured 15 fps 1280x720. NOT run: real webcam, mid-stream drop reconnect; no RtspFrameSource unit test. Limits: frames_dropped ~ total until a consumer reads slot; decode_ms cumulative mean |
| 4. SSE stats to dashboard + dev.ps1 | done | `3489d83` | deferred | 11 pytest, build, lint pass; synthetic publisher -> /api/events (direct + vite proxy) fps ~15, StatsPanel renders. Deviation: dev.ps1 runs uvicorn without --reload (plan said --reload). Also fixed phase 3 bug av.AVError -> av.FFmpegError in `720ab7e`. NOT run: real webcam, interactive Ctrl+C, SSE reconnect |
| Cross-Validation | done | `67215bb`, `ec70458`, `df4c3fc` | 0 Must, 6 Should fixed | 2 oxlint exhaustive-deps warnings on intentional `runRef.current++` in cleanup, left as is |

### Cross-Validation

- Should fix, all fixed: RTSP reader dies on non-FFmpeg exceptions (`67215bb`); bad SOURCE_URL fails silently (`67215bb`); SSE hook never reconnects, Stop/double-click race leaks, misleading Dropped row, vite port drift (`ec70458`); docs `--reload` drift (`df4c3fc`).
- Gaps vs requirements: real-webcam run not done. Fix commits not re-reviewed; verified only by ruff, 14 pytest, client build and lint.
- Nice to have, not done: uvicorn graceful shutdown with open SSE tab; stale frame after source loss (add seq/age check in M2); lazy bgr24 conversion; per-packet decode error handling; ICE state handling in whip/whep; `negotiate` lives in whip.ts; STREAM_PATH doubles as camera_id; dev.ps1 orphan edge; stats not shown next to video (stacked below).

## Final Status

All 4 steps implemented on `feature/webcam-fps-ingest` (not pushed). Verified: ruff, 14 pytest, client build, lint; synthetic 720p@15 H.264 publisher -> MediaMTX -> Python measured about 15 fps, shown via SSE in the dashboard (direct and Vite proxy). NOT verified: a real webcam through browser WHIP, H.264 negotiation, WHEP playback, Stop/DELETE, race fixes in a browser, SSE reconnect. Next: run `.\dev.ps1`, open http://localhost:5173, Start Camera, Connect, confirm video plus FPS in the panel, then open a PR into `dev` (needs explicit push approval).
