// Mirrors server/app/events/schema.py. Null until the first frame is decoded.
export interface StatsEvent {
  camera_id: string;
  fps: number;
  width: number | null;
  height: number | null;
  decode_ms: number | null;
  frames_total: number;
  // Frames overwritten before detection consumed them (about ingest fps minus inference fps per second, by design).
  frames_dropped: number;
  // Null until the detection pipeline has produced a result.
  inference_fps: number | null;
  inference_ms_p50: number | null;
  inference_ms_p95: number | null;
  e2e_latency_ms: number | null;
  pipeline_status?: "loading" | "running" | "failed" | null;
}

export interface Track {
  track_id: number;
  class: string;
  conf: number;
  // normalized 0-1
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface DetectionsEvent {
  camera_id: string;
  frame_ts: number;
  latency_ms: number;
  tracks: Track[];
}
