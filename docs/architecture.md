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
                              |                  Detector (ultralytics YOLO, CPU)
                              |                       v
                              |                  Tracker (ByteTrack via Roboflow `trackers`)
                              |                       v
                              |                  Behavior rules -> alerts (stored with snapshot)
                              |                       v
                              |                  Event bus (in-process)
                              |                       v
                              +--WHEP--> Dashboard <--SSE-- FastAPI (/api/events)
```

Real CCTV later: MediaMTX pulls the camera's RTSP stream. Nothing downstream changes.

## Modules (`server/app/`)

| Module | Responsibility |
|---|---|
| `sources/` | `FrameSource` interface; `RtspFrameSource`, `FileFrameSource` (mp4: looping and paced by default; once and unpaced for replay) |
| `detection/` | `Detection`, `Detector`, `YoloDetector`, `FakeDetector`. `detect(image) -> list[Detection]` |
| `tracking/` | `PersonTracker`, `TrackedDetection`; ByteTrack from Roboflow's `trackers` package (Apache-2.0) |
| `behavior/` | Zones file loading, `Rule` protocol, `BehaviorEngine`, `DwellRule`: rules over tracks -> alerts |
| `alerts/` | `AlertService` (engine alert -> stored evidence + bus event), `AlertStore` (file-based), snapshot rendering |
| `events/` | Pydantic schemas (`StatsEvent`, `DetectionsEvent`, `Track`, `AlertEvent`), SSE formatting, in-process pub/sub: `EventBus` (thread-safe, non-blocking publish; bounded queue per SSE subscriber) |
| `api/` | FastAPI routes, SSE |
| `pipeline.py` | Newest frame -> detect -> track -> rules -> publish; `tools/eval.py` reuses its per-frame step |
| `config.py` | Settings from environment variables (one camera) |

Dependency direction (`->` means imports):

- `api -> alerts -> events`, and `api -> events`
- `behavior -> tracking -> detection -> config`
- `pipeline.py -> sources, detection, tracking, behavior, events, metrics.py`

`main.py` wires everything together and is the only module that imports `api`.

## Layout

```
client/            React + Vite + TS (exists)
server/            FastAPI, uv, ruff, pytest; tools/eval.py replays labelled clips
infra/mediamtx.yml
docs/
dev.ps1            starts MediaMTX, uvicorn (no --reload), vite
```

## Policies

- The browser asks the camera for 1280x720 @ 15 fps (`ideal` constraints).
- Inference sample rate: 5 FPS default, configurable, test 10. ByteTrack assumes small motion between frames, so fast movers may need a higher rate.
- Dwell alerts: a person's box bottom-centre must stay in a zone for the zone's `dwell_s` (no default; a zone without it raises none). A visit lasts while the track was last seen inside at most 2 s ago, so shorter absences (undetected, or seen outside) keep the timer running. One alert per visit and (zone, track). A new track ID starts at zero.
- Video-time base: rules use each frame's `src_ts`, not the wall clock. It is seconds of source time, 0 at the first frame and never going backwards, taken from stream timestamps (monotonic clock if a session's first frame has none). A live source includes reconnect outages; a file does not, and a looping file keeps counting up.
- Latency target: under 3 s from event to dashboard alert. Measure it; the server logs trigger-to-publish time per alert.
- Process model (POC): one process, reader thread + inference thread + FastAPI. Events are JSON-serializable, so a per-camera worker process split later needs no module changes.
- Event delivery: the bus is in-process and bounded per subscriber (32 events). A slow SSE subscriber drops its **oldest** events (non-alert events first) and receives the newest, so a stalled dashboard falls behind rather than back-pressuring ingest. No cross-process bus yet.

## SSE contract

`GET /api/events?camera_id=...`. Vite dev proxy forwards `/api`.

- `detections`: `camera_id`, `frame_ts`, `latency_ms`, `tracks[]` (`track_id`, `class`, `conf`, `x1`, `y1`, `x2`, `y2`). About 5/s, published even when `tracks` is empty.
- `alert`: `alert_id`, `camera_id`, `type`, `score` (0-100, fixed per rule), `reason`, `zone` (optional, null when the alert has no zone), `track_ids`, `src_ts` (video time of the trigger), `ts` (wall clock), `evidence_url`. Sent with SSE `id:` equal to `alert_id`.
- `stats`: `camera_id`, `fps`, `width`, `height`, `decode_ms`, `frames_total`, `frames_dropped`, `inference_fps`, `inference_ms_p50`, `inference_ms_p95`, `e2e_latency_ms`, `pipeline_status`. 1/s. Everything from `width` on is nullable; the four `inference_*`/`e2e_latency_ms` fields are `None` until the detection pipeline has produced a result. `pipeline_status` is `loading`, `running` or `failed`, and `None` when there is no pipeline (`DETECTOR=none`).

An unknown `camera_id` is a 404. A request with a valid `Last-Event-ID` header first replays this camera's stored alerts newer than that id, oldest first, then continues live.

Boxes are flat, normalized 0-1 fields (`x1,y1,x2,y2`), not a nested `bbox` object. TS types are hand-written in `client/src/types/` first; codegen from pydantic schema later.

## Other endpoints

- `GET /api/alerts?limit=&camera_id=`: stored alerts, newest first. `limit` is 1-500, default 50; `camera_id` is optional.
- `GET /api/alerts/{alert_id}/snapshot.jpg`: the alert's JPEG; 404 if unknown or missing.
- `GET /api/zones?camera_id=`: the loaded zones as `name`, `polygon`, `dwell_s` (null if unset); 404 for an unknown camera.

## Dashboard video

WHEP from MediaMTX, boxes on a `<canvas>` overlay. Boxes lag video by roughly inference latency (<1 s). Exact sync (RTP timestamps) is deferred. The overlay also draws the zones, and a list shows alerts, newest first, with snapshot thumbnails.

## Evidence storage

No database. Each alert is a folder `server/data/alerts/<alert_id>/` with `alert.json` and an annotated `snapshot.jpg` (`ALERTS_DIR` changes the root). All access goes through `AlertStore`. Alerts older than `ALERT_RETENTION_DAYS` (default 7) are removed at startup and then hourly. If the folder cannot be used, alerts are disabled and the rest of the server runs.

## Compute

POC: CPU only (Ryzen 7 5700X, AMD RX 580, no CUDA). Detection is `ultralytics` on CPU PyTorch, `yolo11n.pt`, person class only, torch capped at 4 threads (`torch.set_num_threads`). Measured on this machine: about 29.6 ms per frame at 1280x720 (blank frame, 4 threads; p95 31.7 ms), roughly 33 FPS of headroom above the 5 FPS inference target.

The weights live at `server/models/yolo11n.pt` (`models/` is gitignored), so they are not in the repo. A missing model file raises `FileNotFoundError` naming the path, before torch is imported — ultralytics would otherwise treat a bare name as a download request. `YOLO_OFFLINE=1` is set to block ultralytics telemetry and its GitHub asset checks; it must be in the environment before the **first** ultralytics import in the process, because the online flag is read once, at import time (`ultralytics.utils.ONLINE = is_online()`). Setting it later has no effect.

ONNX Runtime is deferred until measured inference is too slow. Moving to an NVIDIA GPU means a runtime provider change plus drivers; a bigger model is a config change if the detector stays behind its interface.

## Build order (cheapest wins first)

Built so far: step 1, and a dwell-in-zone (loitering) rule from step 3.

1. Person detection, boxes, tracking IDs.
2. COCO threat objects: `knife`, `baseball bat`, `backpack`, `handbag`.
3. Track-based rules: group of 3+ moving fast toward a door zone, loitering, running. `yolo11n.pt` already loads the four COCO classes in step 2, and the tracker already exists, so this is rules only, no new model.
4. Pretrained open gun/mask models (check licenses).
5. Custom training for what is missing (machete, stick, face covering).

COCO has no gun, machete, mask or helmet classes. `yolo11n.pt` does load all 80 COCO classes — including `knife` (43), `baseball bat` (34), `backpack` (24) and `handbag` (26) — so the threat classes in step 2 need detection-wiring, not a new model. The model (and its weak accuracy on those classes), not FPS, is the main limit.

## Known debts and risks

- `ultralytics` is AGPL-3.0. Fine for POC; before any commercial use, buy a license or swap to an Apache/MIT detector (RT-DETR, YOLOX, ...). Mitigation: `Detector` interface.
- No auth. MediaMTX accepts any publisher by default. Bind FastAPI and MediaMTX to `127.0.0.1`. Add MediaMTX publish auth and API auth before anything leaves the machine.
- No face recognition or biometric storage by design. "Face covering" is a yes/no attribute only.
- Retention is age-based only; review the policy before real deployment. CCTV analytics has legal rules that vary by country; check before deployment.
- Vendor/paper latency and accuracy claims are not verified benchmarks. Measure on our own footage.
- Browser codec: prefer H.264 (`setCodecPreferences`), VP8 fallback. Verify negotiation in the target browser.
- Track identity: Roboflow `trackers` ByteTrack (Apache-2.0). A track that goes unseen for more than about 2 s (10 inference frames at 5 FPS) is dropped; the person then gets a new ID after 2 consecutive matches.
