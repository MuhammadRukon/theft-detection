import { useEffect, useRef, useState } from "react";
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
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);

  // The <dialog> stays mounted: closing it through close() (or Escape) is what makes the
  // browser return focus to the thumbnail.
  const show = (url: string) => {
    setOpen(url);
    dialogRef.current?.showModal();
  };
  const close = () => dialogRef.current?.close();

  return (
    <div className="p-6">
      <h1 className="mb-4 text-2xl font-bold">Alerts</h1>
      {alerts.length === 0 && <p className="text-gray-500">No alerts yet.</p>}
      <ul className="flex max-w-2xl flex-col gap-2">
        {alerts.map((a) => {
          const age = Math.max(0, now / 1000 - a.ts);
          const label = a.zone === null ? a.type : `${a.type} in ${a.zone}`;
          return (
            <li
              key={a.alert_id}
              className={`flex gap-3 rounded-lg border p-2 transition-colors duration-1000 ${
                age < NEW_S ? "border-amber-400 bg-amber-100" : "border-gray-200"
              }`}
            >
              <button
                type="button"
                onClick={() => show(a.evidence_url)}
                aria-label={label}
                className="shrink-0"
              >
                <img
                  src={a.evidence_url}
                  loading="lazy"
                  alt={label}
                  className="h-16 w-28 rounded bg-black object-cover"
                />
              </button>
              <div className="min-w-0 flex-1 text-left">
                <div className="flex items-center gap-2">
                  <span className="font-semibold">
                    {a.zone === null ? a.type : `${a.type} · ${a.zone}`}
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
      <dialog
        ref={dialogRef}
        aria-label="Alert snapshot"
        onClose={() => setOpen(null)}
        onClick={(e) => {
          // The dialog fills the window: a click on it, not on a child, is the dark area.
          if (e.target === e.currentTarget) close();
        }}
        className="m-0 h-full max-h-none w-full max-w-none flex-col items-center justify-center gap-4 border-0 bg-black/80 p-6 open:flex"
      >
        {open && <img src={open} alt="Alert snapshot" className="min-h-0 max-w-full object-contain" />}
        <button
          type="button"
          onClick={close}
          className="shrink-0 rounded bg-red-600 px-3 py-1 text-white"
        >
          Close
        </button>
      </dialog>
    </div>
  );
}
