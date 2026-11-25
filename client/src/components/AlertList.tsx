import { useEffect, useState } from "react";
import type { AlertEvent } from "../types/events";

const NEW_S = 5; // highlight alerts younger than this

function ago(s: number) {
  if (s < 5) return "just now";
  if (s < 60) return `${Math.floor(s)} s ago`;
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  return `${Math.floor(s / 3600)} h ago`;
}

export default function AlertList({ alerts }: { alerts: AlertEvent[] }) {
  const [now, setNow] = useState(() => Date.now());
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);

  return (
    <div className="p-6">
      <h1 className="mb-4 text-2xl font-bold">Alerts</h1>
      {alerts.length === 0 && <p className="text-gray-500">No alerts yet.</p>}
      <ul className="flex max-w-2xl flex-col gap-2">
        {alerts.map((a) => {
          const age = Math.max(0, now / 1000 - a.ts);
          return (
            <li
              key={a.alert_id}
              className={`flex gap-3 rounded-lg border p-2 transition-colors duration-1000 ${
                age < NEW_S ? "border-amber-400 bg-amber-100" : "border-gray-200"
              }`}
            >
              <button type="button" onClick={() => setOpen(a.evidence_url)} className="shrink-0">
                <img
                  src={a.evidence_url}
                  loading="lazy"
                  alt={`${a.type} in ${a.zone}`}
                  className="h-16 w-28 rounded bg-black object-cover"
                />
              </button>
              <div className="min-w-0 flex-1 text-left">
                <div className="flex items-center gap-2">
                  <span className="font-semibold">
                    {a.type} · {a.zone}
                  </span>
                  <span className="rounded bg-red-600 px-1.5 text-xs text-white">{a.score}</span>
                  <span className="ml-auto text-sm text-gray-500">{ago(age)}</span>
                </div>
                <p className="text-sm">{a.reason}</p>
              </div>
            </li>
          );
        })}
      </ul>
      {open && (
        <div
          className="fixed inset-0 z-10 flex items-center justify-center bg-black/80 p-6"
          onClick={() => setOpen(null)}
        >
          <img src={open} alt="Alert snapshot" className="max-h-full max-w-full" />
        </div>
      )}
    </div>
  );
}
