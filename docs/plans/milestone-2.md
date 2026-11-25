# Milestone 2: person detection without breaking real-time ingestion

See [architecture](../architecture.md) and [milestone 1](milestone-1.md). No database, Redis or Kafka. Goal: prove the detection pipeline works in real time.

**Done when:** the dashboard shows boxes with stable track IDs over the live webcam video, ingest FPS stays near 15 while inference runs, and the stats panel shows inference FPS, p50/p95 inference ms and end-to-end latency. Target is under 1 s capture-to-SSE latency on this CPU; if it misses, report the number rather than tune it away.

## Decisions (from grilling)

- **Runtime:** `ultralytics` with CPU PyTorch behind the `Detector` interface, person class only. ONNX export later, only if measured inference is too slow. (Deviation from the architecture doc's "ONNX Runtime"; update that line when this lands.)
- **Model:** pretrained `yolo11n.pt` (COCO nano, about 5 MB) from the official `ultralytics/assets` GitHub release. Ask the user before each download, naming file, source, size. AGPL-3.0 debt stays recorded.
- **CPU budget:** detection in its own thread, torch capped at 4 threads, inference target 5 FPS (configurable), newest frame only, older frames dropped. Tracker frame rate = inference rate. Ingest must stay about 15 FPS; report ingest and inference numbers separately.
- **Events:** small in-process bus in `app/events/` (push; slow subscribers drop old messages). Tracker is `supervision` ByteTrack (MIT).
- **Overlay:** canvas over the WHEP video, sized to the displayed video rectangle (not the element) so letterboxing does not shift boxes. Show track ID and confidence. Boxes lag video by pipeline latency. Clear boxes after about 1 s without detections.
- **Tests:** use `FileFrameSource` plus a fake detector. No model needed in CI.

## Git

Branch from `main` per git-hygiene, but `main` has only the empty initial commit and Milestone 1 lives on `feature/webcam-fps-ingest` (not merged). Decide at setup: stack the new branch on the milestone 1 branch (recommended) or wait for the merge.

## Phases

### 1. Event bus and SSE contract

- `app/events/`: in-process pub/sub (thread-safe publish from worker threads into asyncio subscribers, bounded per-subscriber queue that drops oldest). Pydantic `DetectionsEvent` (`camera_id`, `frame_ts`, `latency_ms`, `tracks[]` with `track_id`, `class`, `conf`, bbox normalized 0-1 `x1,y1,x2,y2`). Extend `StatsEvent` with `inference_fps`, `inference_ms_p50`, `inference_ms_p95`, `e2e_latency_ms` (all nullable).
- `GET /api/events` keeps the 1 s `stats` event and also streams `detections` from the bus. Clean unsubscribe on disconnect.
- Tests: bus drop-oldest, thread-to-async publish, SSE formatting for both events.
- AC: pytest + ruff pass; a test publishes from a thread and a subscriber receives it.

### 2. Detector

- `app/detection/`: `Detection` dataclass, `Detector` ABC (`detect(image) -> list[Detection]`), `YoloDetector` (ultralytics, `yolo11n.pt`, `classes=[0]`, CPU, `torch.set_num_threads(4)`), `FakeDetector` for tests. Config via `Settings` (model path, conf threshold, threads).
- Add `ultralytics` and CPU torch to `server/pyproject.toml` (ask before the model download; torch wheels come from the package index).
- AC: unit tests with `FakeDetector`; one manual check that `YoloDetector` loads and detects a person in a sample image, with measured ms per frame on this CPU.

### 3. Processing loop and tracker

- `app/tracking/`: ByteTrack wrapper over `supervision` (frame rate from inference rate), takes `list[Detection]`, returns tracks with persistent IDs.
- `app/pipeline.py` (or `processing/`): thread that takes the newest frame from the source, skips if no new frame, runs detector then tracker, records inference ms (rolling p50/p95), inference FPS and end-to-end latency (frame decode timestamp to publish), publishes `DetectionsEvent` to the bus, rate-limited to the target FPS. Source ingest is unaffected (frames overwritten, never queued).
- Wire into `main.py` lifespan with clean stop. Stats feed the extended `StatsEvent`.
- Tests: loop with `FileFrameSource` + `FakeDetector` (processes newest frame, drops when slow, publishes events, stops promptly); tracker keeps IDs across frames for a moving box.
- AC: pytest + ruff pass; with a deliberately slow fake detector, ingest FPS stays at the native rate and inference FPS reports the lower rate.

### 4. Dashboard overlay

- Client: TS types for `detections` and extended stats; `useDetections` hook (reuse the SSE connection or share one EventSource with `useStats`); `DetectionOverlay` canvas over the viewer video, drawn on the displayed video rectangle, with track ID and confidence, cleared after about 1 s of silence; stats panel shows inference FPS, p50/p95 inference ms, e2e latency next to ingest FPS.
- AC: `bun run build` and `bun run lint` pass.

### 5. End-to-end verification and docs

- Real webcam in Chrome (user's camera, Claude in Chrome): boxes with stable IDs follow a person, ingest FPS near 15, panel shows the new numbers. Record measured inference FPS, p50/p95 and latency, and whether the under 1 s target is met.
- Update `docs/architecture.md` (runtime line, module list, SSE contract).
- Cross-validation pass over the whole diff as in milestone 1.

## Out of scope

Weapons, other classes, behavior rules, alerts and evidence store, ONNX export, GPU, multi-camera registry, auth, database/Redis/Kafka.

## Execution Progress

**Status: in progress**

_Last updated: 2026-11-26 — Branch: feature/person-detection (stacked on feature/webcam-fps-ingest) — Workspace: main working directory_

Final commit list: —

| Phase | Status | Commit | Review | Notes |
| --- | --- | --- | --- | --- |
| 1. Event bus and SSE | pending | — | deferred | — |
| 2. Detector | pending | — | deferred | ask user before model and torch downloads |
| 3. Processing loop and tracker | pending | — | deferred | — |
| 4. Dashboard overlay | pending | — | deferred | — |
| 5. E2E check, docs, cross-validation | pending | — | — | — |
