# Architecture

Modular, real-time computer-vision surveillance system. Starts with person detection, grows into contextual theft-risk detection. POC first, but no major rework on the way to production.

## Principles

1. Video and detection events are separate channels. Boxes are never burned into video.
2. No per-frame JPEG upload. Video travels as a real stream.
3. Camera ingestion is independent of AI models.
4. Detection is independent of the frontend.
5. Drop frames, never accumulate delay (latest-frame-wins slot).
6. Detection, tracking and behavior analysis are separate modules.
7. Every pipeline, event and track ID is keyed by `camera_id` from day one.

## Data flow

```
Webcam (browser) --WHIP--> MediaMTX --RTSP--> FrameSource (PyAV reader thread)
                              |                       |
                              |                  latest-frame slot
                              |                       v
                              |                  Detector (YOLO/ONNX)
                              |                       v
                              |                  Tracker (ByteTrack via supervision)
                              |                       v
                              |                  Behavior rules -> risk events
                              |                       v
                              |                  Event bus (in-process)
                              |                       v
                              +--WHEP--> Dashboard <--SSE-- FastAPI (/api/events)
```

Real CCTV later: MediaMTX pulls the camera's RTSP stream. Nothing downstream changes.

## Modules (`server/app/`)

| Module | Responsibility |
|---|---|
| `sources/` | `FrameSource` interface; `RtspFrameSource`, `FileFrameSource` (looping mp4 for tests) |
| `detection/` | `Detector.detect(frame) -> list[Detection]`; YOLO/ONNX impl |
| `tracking/` | Takes `Detection` list, returns tracks with persistent IDs (`supervision` ByteTrack, MIT) |
| `behavior/` | Rules over tracks -> risk events (later) |
| `events/` | Pydantic schemas, in-process pub/sub |
| `store/` | `AlertStore` interface; file-based impl |
| `api/` | FastAPI routes, SSE |
| `config.py` | FPS, thresholds, camera list |

Dependency direction: `api -> events <- behavior <- tracking <- detection <- sources`. Nothing imports `api`.

## Layout

```
client/            React + Vite + TS (exists)
server/            FastAPI, uv, ruff, pytest
infra/mediamtx.yml
docs/
dev.ps1            starts MediaMTX, uvicorn --reload, vite
```

## Policies

- Camera sends 1280x720 @ 15 fps.
- Inference sample rate: 5 FPS default, configurable, test 10. ByteTrack assumes small motion between frames, so fast movers may need a higher rate.
- Alert confirmation: N-of-M (default 3 of 5) plus per-camera cooldown.
- Latency target: under 3 s from event to dashboard alert. Measure it.
- Process model (POC): one process, reader thread + inference thread + FastAPI. Events are JSON-serializable, so a per-camera worker process split later needs no module changes.

## SSE contract

`GET /api/events?camera_id=...`. Vite dev proxy forwards `/api`.

- `detections`: `camera_id`, `frame_ts`, `latency_ms`, `tracks[]` (`track_id`, `class`, `conf`, `bbox`). About 5/s.
- `alert`: `alert_id`, `camera_id`, `type`, `risk_score`, `track_ids`, `evidence_url`. Sent with SSE `id:` so `Last-Event-ID` resumes after reconnect.
- `stats`: incoming FPS, resolution, inference FPS, dropped frames. 1/s.

Boxes are normalized 0-1 (`x1,y1,x2,y2`). TS types are hand-written in `client/src/types/` first; codegen from pydantic schema later.

## Dashboard video

WHEP from MediaMTX, boxes on a `<canvas>` overlay. Boxes lag video by roughly inference latency (<1 s). Exact sync (RTP timestamps) is deferred.

## Evidence storage

No database. Each alert is a folder `server/data/alerts/<alert_id>/` with `alert.json` and an annotated `snapshot.jpg`. Short clip later. All access via `AlertStore`; swap to SQLite/Postgres later.

## Compute

POC: CPU only (Ryzen 7 5700X, AMD RX 580, no CUDA). Nano model exported to ONNX Runtime. Moving to an NVIDIA GPU means a runtime provider change plus drivers; a bigger model is a config change if the detector stays behind its interface.

## Build order (cheapest wins first)

1. Person detection, boxes, tracking IDs.
2. COCO threat objects: `knife`, `baseball bat`, `backpack`, `handbag`.
3. Track-based rules, no new model: group of 3+ moving fast toward a door zone, loitering, running.
4. Pretrained open gun/mask models (check licenses).
5. Custom training for what is missing (machete, stick, face covering).

COCO has no gun, machete, mask or helmet classes. The model, not FPS, is the main accuracy limit.

## Known debts and risks

- `ultralytics` is AGPL-3.0. Fine for POC; before any commercial use, buy a license or swap to an Apache/MIT detector (RT-DETR, YOLOX, ...). Mitigation: `Detector` interface.
- No auth. MediaMTX accepts any publisher by default. Bind FastAPI and MediaMTX to `127.0.0.1`. Add MediaMTX publish auth and API auth before anything leaves the machine.
- No face recognition or biometric storage by design. "Face covering" is a yes/no attribute only.
- Snapshot retention policy needed before real deployment. CCTV analytics has legal rules that vary by country; check before deployment.
- Vendor/paper latency and accuracy claims are not verified benchmarks. Measure on our own footage.
- Browser codec: prefer H.264 (`setCodecPreferences`), VP8 fallback. Verify negotiation in the target browser.
