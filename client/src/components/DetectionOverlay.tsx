import { useEffect, useRef } from "react";
import type { RefObject } from "react";
import { containRect } from "../lib/videoRect";
import type { DetectionsEvent, Zone } from "../types/events";

const STALE_MS = 1000;

// Stable color per track id (golden-angle hue spread).
const color = (id: number) => `hsl(${(id * 137.5) % 360} 90% 55%)`;

export default function DetectionOverlay({
  videoRef,
  detections,
  zones,
  active,
}: {
  videoRef: RefObject<HTMLVideoElement | null>;
  detections: DetectionsEvent | null;
  zones: Zone[];
  active: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // Latest data lives in a ref so the observers below are set up once, not per 5 Hz event.
  const latest = useRef({ detections, zones, active, at: 0 });
  const drawRef = useRef<() => void>(() => {});

  useEffect(() => {
    const canvas = canvasRef.current;
    const video = videoRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !video || !ctx) return;

    const draw = () => {
      const dpr = window.devicePixelRatio || 1;
      const { clientWidth: cw, clientHeight: ch } = canvas;
      const w = Math.round(cw * dpr);
      const h = Math.round(ch * dpr);
      // Assigning width/height reallocates the backing store, so only do it on change.
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const { detections: d, zones: zs, active: on, at } = latest.current;
      if (!on) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const r = containRect(video.videoWidth, video.videoHeight, cw, ch);
      ctx.font = "12px sans-serif";
      ctx.textBaseline = "top";
      ctx.lineWidth = 2;
      // Zones are static config, so they stay up when detections go stale.
      for (const z of zs) {
        ctx.beginPath();
        z.polygon.forEach(([px, py], i) => {
          const x = r.x + px * r.w;
          const y = r.y + py * r.h;
          if (i) ctx.lineTo(x, y);
          else ctx.moveTo(x, y);
        });
        ctx.closePath();
        ctx.strokeStyle = ctx.fillStyle = "#facc15";
        ctx.globalAlpha = 0.2;
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.setLineDash([6, 4]);
        ctx.stroke();
        ctx.setLineDash([]);
        const [lx, ly] = z.polygon[0];
        const text = z.dwell_s === null ? z.name : `${z.name} (${z.dwell_s} s)`;
        ctx.fillText(text, r.x + lx * r.w + 4, r.y + ly * r.h + 4);
      }
      if (!d || performance.now() - at >= STALE_MS) return;
      for (const t of d.tracks) {
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

    drawRef.current = draw;
    const ro = new ResizeObserver(draw);
    ro.observe(canvas);
    video.addEventListener("loadedmetadata", draw);
    video.addEventListener("resize", draw); // WebRTC can change resolution mid-stream
    return () => {
      ro.disconnect();
      video.removeEventListener("loadedmetadata", draw);
      video.removeEventListener("resize", draw);
    };
  }, [videoRef]);

  useEffect(() => {
    // Stamp only on new detections so toggling `active` never revives old boxes.
    const at = latest.current.detections === detections ? latest.current.at : performance.now();
    latest.current = { detections, zones, active, at };
    drawRef.current();
    const timer = window.setTimeout(() => drawRef.current(), STALE_MS);
    return () => window.clearTimeout(timer);
  }, [detections, zones, active]);

  return <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 h-full w-full" />;
}
