import { useEffect, useState } from "react";
import type { StatsEvent } from "../types/events";

export type StatsConnection = "connecting" | "open" | "closed";

export function useStats(cameraId: string) {
  const [stats, setStats] = useState<StatsEvent | null>(null);
  const [connection, setConnection] = useState<StatsConnection>("connecting");

  useEffect(() => {
    const es = new EventSource(`/api/events?camera_id=${encodeURIComponent(cameraId)}`);
    es.onopen = () => setConnection("open");
    // EventSource retries by itself while CONNECTING; CLOSED means it gave up (e.g. 404).
    es.onerror = () => setConnection(es.readyState === EventSource.CLOSED ? "closed" : "connecting");
    es.addEventListener("stats", (e) => setStats(JSON.parse((e as MessageEvent).data)));
    return () => es.close();
  }, [cameraId]);

  return { stats, connection };
}
