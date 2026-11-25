import { useEffect, useRef } from "react";
import type { RefObject } from "react";
import { containRect } from "../lib/videoRect";
import type { DetectionsEvent } from "../types/events";

const STALE_MS = 1000;

// Stable color per track id (golden-angle hue spread).
const color = (id: number) => `hsl(${(id * 137.5) % 360} 90% 55%)`;

export default function DetectionOverlay({
  videoRef,
  detections,
  active,
}: {
  videoRef: RefObject<HTMLVideoElement | null>;
  detections: DetectionsEvent | null;
  active: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const video = videoRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !video || !ctx) return;

    let show = active && detections != null;
    const draw = () => {
      const dpr = window.devicePixelRatio || 1;
      const { clientWidth: cw, clientHeight: ch } = canvas;
      canvas.width = Math.round(cw * dpr); // also clears
      canvas.height = Math.round(ch * dpr);
      if (!show || !detections) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const r = containRect(video.videoWidth, video.videoHeight, cw, ch);
      ctx.font = "12px sans-serif";
      ctx.textBaseline = "top";
      ctx.lineWidth = 2;
      for (const t of detections.tracks) {
        const x = r.x + t.x1 * r.w;
        const y = r.y + t.y1 * r.h;
        const label = `#${t.track_id} ${Math.round(t.conf * 100)}%`;
        ctx.strokeStyle = ctx.fillStyle = color(t.track_id);
        ctx.strokeRect(x, y, (t.x2 - t.x1) * r.w, (t.y2 - t.y1) * r.h);
        ctx.fillRect(x, y, ctx.measureText(label).width + 6, 16);
        ctx.fillStyle = "#000";
        ctx.fillText(label, x + 3, y + 2);
      }
    };

    draw();
    const timer = window.setTimeout(() => {
      show = false;
      draw();
    }, STALE_MS);
    const ro = new ResizeObserver(draw);
    ro.observe(canvas);
    video.addEventListener("loadedmetadata", draw);
    return () => {
      window.clearTimeout(timer);
      ro.disconnect();
      video.removeEventListener("loadedmetadata", draw);
    };
  }, [videoRef, detections, active]);

  return <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 h-full w-full" />;
}
