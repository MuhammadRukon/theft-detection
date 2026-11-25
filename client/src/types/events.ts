// Mirrors server/app/events/schema.py. Null until the first frame is decoded.
export interface StatsEvent {
  camera_id: string;
  fps: number;
  width: number | null;
  height: number | null;
  decode_ms: number | null;
  frames_total: number;
  frames_dropped: number;
}
