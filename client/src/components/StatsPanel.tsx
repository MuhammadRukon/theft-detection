import type { EventsConnection } from "../hooks/useCameraEvents";
import type { StatsEvent } from "../types/events";

const dash = "-";
const ms = (v: number | null | undefined) => (v != null ? `${v} ms` : dash);
const fixed = (v: number | null | undefined) => (v != null ? v.toFixed(1) : dash);

export default function StatsPanel({
  stats,
  connection,
}: {
  stats: StatsEvent | null;
  connection: EventsConnection;
}) {
  return (
    <div className="p-6">
      <h1 className="mb-4 text-2xl font-bold">Incoming stream</h1>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2">
        <dt>FPS</dt>
        <dd>{fixed(stats?.fps)}</dd>
        <dt>Resolution</dt>
        <dd>{stats?.width ? `${stats.width}x${stats.height}` : dash}</dd>
        <dt>Decode</dt>
        <dd>{ms(stats?.decode_ms)}</dd>
        <dt>Inference FPS</dt>
        <dd>{fixed(stats?.inference_fps)}</dd>
        <dt>Inference p50 / p95</dt>
        <dd>
          {stats?.inference_ms_p50 != null && stats.inference_ms_p95 != null
            ? `${stats.inference_ms_p50} / ${stats.inference_ms_p95} ms`
            : dash}
        </dd>
        <dt>Server latency (decode→publish)</dt>
        <dd>{ms(stats?.e2e_latency_ms)}</dd>
        <dt>Detector</dt>
        <dd className={stats?.pipeline_status === "failed" ? "font-semibold text-red-600" : undefined}>
          {stats?.pipeline_status ?? dash}
        </dd>
      </dl>
      <p className="mt-3 text-sm text-gray-500">Events: {connection}</p>
    </div>
  );
}
