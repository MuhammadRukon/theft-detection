# Theft detection (proof of concept)

A modular, real-time computer-vision surveillance POC. A webcam stream goes to MediaMTX over WebRTC (WHIP). The Python server reads it over RTSP, detects and tracks people, and applies a simple "dwell in a zone" rule. The React dashboard shows the live video with boxes and zones, stats, and alerts.

This is a proof of concept: no authentication, no database, CPU-only inference, one camera, one rule.

```
Browser webcam --WHIP--> MediaMTX --RTSP--> Python server
                            |                 reader -> YOLO (person) -> ByteTrack -> dwell rule
                            |                                   |
                            +--WHEP--> Dashboard <----SSE-------+  (stats, detections, alerts)
```

Video and events travel on separate channels. Details: [docs/architecture.md](docs/architecture.md).

## Requirements

- Windows with PowerShell
- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- [bun](https://bun.sh/)

## Setup

1. Client dependencies:

```powershell
cd client; bun install; cd ..
```

2. Server dependencies (installs CPU PyTorch and ultralytics; several hundred MB):

```powershell
cd server; uv sync; cd ..
```

3. MediaMTX. The binary is gitignored and not in the repo. Download `mediamtx_v1.21.4_windows_amd64.zip` from the [MediaMTX releases](https://github.com/bluenviron/mediamtx/releases) and put `mediamtx.exe` at `infra\bin\mediamtx.exe`.

4. YOLO model. `server\models\yolo11n.pt` is gitignored. Put the pretrained `yolo11n.pt` (from the official ultralytics assets release) there. Without it the server refuses to start the detector and says so; ingest and the dashboard still work.

5. Run everything:

```powershell
.\dev.ps1
```

## Use it

Open `http://localhost:5173` (or `http://127.0.0.1:5173`; these are the only origins MediaMTX allows). Click **Start Camera**, allow the webcam, then click **Connect**.

The stats panel shows ingest FPS, resolution, decode time, inference FPS, inference p50/p95, server latency (decode to publish) and a **Detector** row (loading, running or failed). Boxes follow people, coloured per track ID and labelled with the ID and confidence percent (`#3 87%`).

## Dwell alerts

A person standing inside a zone for the zone's `dwell_s` raises one alert per visit. The visit ends once they have not been seen inside for more than 2 s; shorter absences keep the timer running. Zones are polygons in normalized 0-1 coordinates in `server/config/zones.json` (copy `server/config/zones.sample.json`, which is used if the real file is absent; the real file is gitignored). The rule uses the bottom-centre of the person's box, roughly the feet. Each alert is saved with an annotated snapshot under `server/data/alerts/` and sent over SSE; `GET /api/alerts` lists them and `GET /api/zones?camera_id=cam1` returns the loaded zones.

## Replay and evaluation

Recorded clips can be replayed through the real pipeline and scored against label files. See [docs/recording-clips.md](docs/recording-clips.md), then:

```powershell
cd server; uv run python -m tools.eval
```

## Configuration

Environment variables read by the server (`server/app/config.py`):

| Variable | Default | Meaning |
| --- | --- | --- |
| `CAMERA_ID` | `cam1` | Camera id used in events and zones |
| `SOURCE_URL` | `rtsp://127.0.0.1:8554/cam1` | RTSP URL, or a path to an mp4 (looped) |
| `DETECTOR` | `yolo` | `none` runs ingest and SSE without a model |
| `MODEL_PATH` | `server/models/yolo11n.pt` | YOLO weights |
| `DETECT_CONF` | `0.2` | Detector confidence floor |
| `TRACK_CONF` | `0.4` | Confidence needed to start a track |
| `TORCH_THREADS` | `4` | CPU threads for inference |
| `INFERENCE_FPS` | `5.0` | Target inference rate |
| `ZONES_PATH` | `server/config/zones.json` (else the sample) | Zones file |
| `ALERTS_DIR` | `server/data/alerts` | Alert and snapshot folder |
| `ALERT_RETENTION_DAYS` | `7` | Alerts older than this are removed at startup and then hourly |

## Ports

| Port | What | Reachable from |
| --- | --- | --- |
| 5173 | Vite dev server | localhost |
| 8000 | FastAPI (`/api/events`, `/api/alerts`, `/api/zones`) | localhost |
| 8889 | MediaMTX WHIP/WHEP | localhost |
| 8554 | MediaMTX RTSP | localhost |
| 8189/udp | MediaMTX WebRTC media | **local network** |

UDP 8189 listens on all interfaces so Chrome can connect. A WebRTC session can only be started through the localhost-only HTTP endpoint, but add authentication before exposing any of this.

## Layout

- `client/` React + Vite + TypeScript dashboard
- `server/app/` FastAPI app: `sources/` (RTSP and file frame sources), `detection/`, `tracking/`, `behavior/` (zones, dwell rule), `alerts/` (store, snapshots), `events/` (bus, SSE schemas), `api/`, `pipeline.py`
- `server/tools/eval.py` replay and scoring of recorded clips
- `infra/mediamtx.yml` MediaMTX config (binary not included)
- `docs/` architecture, milestone plans, clip-recording guide

## Known limits

- No authentication anywhere. Do not expose it.
- CPU-only inference (about 30 ms per frame on the dev machine); no GPU path yet.
- ultralytics (code and weights) is AGPL-3.0: commercial use needs a licence or a different detector.
- Detection is intermittent in dim light or when a person fills the frame, and track IDs can switch.
- Camera-to-browser latency is not measured; the server reports decode-to-publish only.
- Only people are detected. No weapons, objects or face attributes yet.
