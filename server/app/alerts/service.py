import logging
import secrets
import time

from app.alerts.snapshot import render_snapshot
from app.alerts.store import AlertStore
from app.events import AlertEvent, EventBus

log = logging.getLogger("alerts")


def new_alert_id() -> str:
    # hex ms timestamp (sortable, fixed length until year 2527) + 4 random hex chars
    return f"{int(time.time() * 1000):011x}{secrets.token_hex(2)}"


class AlertService:
    """Turns a behavior-engine alert into stored evidence + a bus event. Never raises."""

    def __init__(self, store: AlertStore, bus: EventBus, zones_by_camera: dict[str, list]):
        self.store = store
        self.bus = bus
        self.zones_by_camera = zones_by_camera

    def handle(self, alert, image, tracks) -> AlertEvent | None:
        try:
            alert_id = new_alert_id()
            event = AlertEvent(
                alert_id=alert_id,
                camera_id=alert.camera_id,
                type=alert.type,
                score=alert.score,
                reason=alert.reason,
                zone=alert.zone,
                track_ids=list(alert.track_ids),
                src_ts=alert.src_ts,
                ts=alert.ts,
                evidence_url=f"/api/alerts/{alert_id}/snapshot.jpg",
            )
            zones = self.zones_by_camera.get(alert.camera_id, [])
            self.store.save(event, render_snapshot(image, tracks, zones, alert))
            self.bus.publish(event)
            ms = (time.time() - alert.ts) * 1000
            log.info("alert %s published %.0f ms after trigger", alert_id, ms)
            return event
        except Exception:
            log.exception("alert handling failed")
            return None
