import type { ReactNode, RefObject } from "react";

type Props = {
  title: string;
  videoRef: RefObject<HTMLVideoElement | null>;
  startLabel: string;
  stopLabel: string;
  active: boolean;
  busy: boolean;
  error: string | null;
  onStart: () => void;
  onStop: () => void;
  overlay?: ReactNode; // drawn on top of the video
  children: ReactNode; // status line text
};

export default function SessionPanel(p: Props) {
  const { videoRef, active, busy, onStart, onStop } = p;
  return (
    <div className="p-6">
      <h1 className="mb-4 text-2xl font-bold">{p.title}</h1>

      <div className="relative mb-4 w-full max-w-2xl">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className="block w-full rounded-xl bg-black"
        />
        {p.overlay}
      </div>

      <div className="flex gap-3">
        <button
          onClick={onStart}
          disabled={active || busy}
          className="rounded-lg bg-green-600 px-4 py-2 text-white disabled:opacity-50"
        >
          {p.startLabel}
        </button>

        <button
          onClick={onStop}
          disabled={!active}
          className="rounded-lg bg-red-600 px-4 py-2 text-white disabled:opacity-50"
        >
          {p.stopLabel}
        </button>
      </div>

      {p.error && <p className="mt-3 text-red-500">{p.error}</p>}

      <p className="mt-3 text-sm text-gray-500">{p.children}</p>
    </div>
  );
}
