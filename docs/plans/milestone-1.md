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
