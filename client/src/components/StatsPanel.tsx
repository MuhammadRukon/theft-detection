import { STREAM_PATH } from "../lib/config";
import { useStats } from "../hooks/useStats";

export default function StatsPanel() {
  const { stats, connection } = useStats(STREAM_PATH);
  const dash = "-";

  return (
    <div className="p-6">
      <h1 className="mb-4 text-2xl font-bold">Incoming stream</h1>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2">
        <dt>FPS</dt>
        <dd>{stats ? stats.fps.toFixed(1) : dash}</dd>
        <dt>Resolution</dt>
        <dd>{stats?.width ? `${stats.width}x${stats.height}` : dash}</dd>
        <dt>Decode</dt>
        <dd>{stats?.decode_ms != null ? `${stats.decode_ms} ms` : dash}</dd>
        <dt>Dropped</dt>
        <dd>{stats ? `${stats.frames_dropped} / ${stats.frames_total}` : dash}</dd>
      </dl>
      <p className="mt-3 text-sm text-gray-500">Events: {connection}</p>
    </div>
  );
}
