import { useEffect, useState } from "react";
import type { AlertEvent, DetectionsEvent, StatsEvent, Zone } from "../types/events";

export type EventsConnection = "connecting" | "open" | "closed";

const MAX_ALERTS = 50;

// Union by alert_id, newest first (ids are hex timestamps, so string order is time order).
const merge = (a: AlertEvent[], b: AlertEvent[]) =>
  [...new Map([...a, ...b].map((x) => [x.alert_id, x])).values()]
    .sort((x, y) => (x.alert_id < y.alert_id ? 1 : -1))
    .slice(0, MAX_ALERTS);

// One EventSource per camera, shared by everything that shows stats, detections or alerts.
export function useCameraEvents(cameraId: string) {
  const [stats, setStats] = useState<StatsEvent | null>(null);
  const [detections, setDetections] = useState<DetectionsEvent | null>(null);
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [zones, setZones] = useState<Zone[]>([]);
  const [connection, setConnection] = useState<EventsConnection>("connecting");

  useEffect(() => {
    let es: EventSource;
    let timer: number | undefined;
    let stopped = false;
    const id = encodeURIComponent(cameraId);
    // A recreated EventSource cannot send Last-Event-ID, so refetch what was missed on every
    // (re)connect; zones too, in case the server restarted with a different file.
    const sync = () => {
      fetch(`/api/alerts?limit=${MAX_ALERTS}&camera_id=${id}`)
        .then((r) => (r.ok ? r.json() : []))
        .then((a: AlertEvent[]) => stopped || setAlerts((cur) => merge(cur, a)))
        .catch(() => {});
      fetch(`/api/zones?camera_id=${id}`)
        .then((r) => (r.ok ? r.json() : []))
        .then((z: Zone[]) => stopped || setZones(z))
        .catch(() => {});
    };
    const open = () => {
      es = new EventSource(`/api/events?camera_id=${id}`);
      es.onopen = () => {
        setConnection("open");
        sync();
      };
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
      es.addEventListener("alert", (e) =>
        setAlerts((cur) => merge(cur, [JSON.parse((e as MessageEvent).data)])),
      );
    };
    open();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      es.close();
    };
  }, [cameraId]);

  return { stats, detections, alerts, zones, connection };
}
