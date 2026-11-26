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

  // Drive the native <dialog> through the imperative API; Escape, focus trapping
  // and focus return are handled natively.
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open) {
      dialog.showModal();
    } else if (dialog.open) {
      dialog.close();
    }
  }, [open]);

  // Keep React state in sync when the native dialog closes itself (Escape, Close, backdrop).
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const handleClose = () => setOpen(null);
    dialog.addEventListener("close", handleClose);
    return () => dialog.removeEventListener("close", handleClose);
  }, [open]);

  const close = () => setOpen(null);

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
                onClick={() => setOpen(a.evidence_url)}
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
      {open && (
        <dialog
          ref={dialogRef}
          aria-label="Alert snapshot"
          onClick={(e) => {
            // Only the dark backdrop (the dialog element itself) closes; clicks on
            // the image are ignored.
            if (e.target === e.currentTarget) close();
          }}
          className="m-0 fixed inset-0 z-10 flex max-h-full max-w-full flex-col items-center justify-center overflow-hidden rounded bg-black p-6"
        >
          <img src={open} alt="Alert snapshot" className="max-h-full max-w-full rounded" />
          <button
            type="button"
            onClick={close}
            className="mt-4 rounded bg-red-600 px-3 py-1 text-white"
          >
            Close
          </button>
        </dialog>
      )}
    </div>
  );
}
