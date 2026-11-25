import { useEffect, useState } from "react";
import type { DetectionsEvent, StatsEvent } from "../types/events";

export type EventsConnection = "connecting" | "open" | "closed";

// One EventSource per camera, shared by everything that shows stats or detections.
export function useCameraEvents(cameraId: string) {
  const [stats, setStats] = useState<StatsEvent | null>(null);
  const [detections, setDetections] = useState<DetectionsEvent | null>(null);
  const [connection, setConnection] = useState<EventsConnection>("connecting");

  useEffect(() => {
    let es: EventSource;
    let timer: number | undefined;
    const open = () => {
      es = new EventSource(`/api/events?camera_id=${encodeURIComponent(cameraId)}`);
      es.onopen = () => setConnection("open");
      // EventSource retries by itself while CONNECTING; CLOSED means it gave up (e.g. a 500
      // from the proxy while the server restarts), so recreate it after a pause.
      es.onerror = () => {
        if (es.readyState !== EventSource.CLOSED) return setConnection("connecting");
        setConnection("closed");
        es.close();
        timer = window.setTimeout(open, 2000);
      };
      es.addEventListener("stats", (e) => setStats(JSON.parse((e as MessageEvent).data)));
      es.addEventListener("detections", (e) => setDetections(JSON.parse((e as MessageEvent).data)));
    };
    open();
    return () => {
      window.clearTimeout(timer);
      es.close();
    };
  }, [cameraId]);

  return { stats, detections, connection };
}
