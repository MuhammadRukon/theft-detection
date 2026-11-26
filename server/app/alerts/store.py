import logging
import os
import re
import shutil
import threading
import uuid
from pathlib import Path

from app.events import AlertEvent

log = logging.getLogger("alerts")

# Ids are generated as hex (fixed length, time-sortable); anything else never touches the disk.
_ID_RE = re.compile(r"[0-9a-f]{1,32}")


def valid_alert_id(alert_id: str) -> bool:
    return _ID_RE.fullmatch(alert_id) is not None


class AlertStore:
    """One folder per alert: alert.json + snapshot.jpg. Folders appear atomically via rename."""

    def __init__(self, root: Path, retention_days: int):
        self.root = Path(root)
        self.retention_days = retention_days
        self._lock = threading.Lock()
        self._alerts: dict[str, AlertEvent] = {}
        self.root.mkdir(parents=True, exist_ok=True)
        for d in self.root.iterdir():
            if d.name.startswith(".tmp-"):  # left by a save that was killed mid-write
                shutil.rmtree(d, ignore_errors=True)
                continue
            if not d.is_dir() or d.name.startswith("."):
                continue
            try:
                if not valid_alert_id(d.name) or not (d / "snapshot.jpg").is_file():
                    raise ValueError("missing or invalid files")
                ev = AlertEvent.model_validate_json((d / "alert.json").read_text("utf-8"))
                if ev.alert_id != d.name:
                    raise ValueError("id does not match folder")
                self._alerts[ev.alert_id] = ev
            except (OSError, ValueError) as e:  # pydantic ValidationError is a ValueError
                log.warning("ignoring corrupt alert folder %s: %s", d, e)

    def save(self, event: AlertEvent, jpeg: bytes) -> None:
        tmp = self.root / f".tmp-{uuid.uuid4().hex}"
        tmp.mkdir()
        try:
            (tmp / "snapshot.jpg").write_bytes(jpeg)
            (tmp / "alert.json").write_text(event.model_dump_json(), "utf-8")
            os.rename(tmp, self.root / event.alert_id)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        with self._lock:
            self._alerts[event.alert_id] = event

    def list(self, limit: int = 50) -> list[AlertEvent]:
        with self._lock:
            ids = sorted(self._alerts, reverse=True)[:limit]
            return [self._alerts[i] for i in ids]

    def get(self, alert_id: str) -> AlertEvent | None:
        with self._lock:
            return self._alerts.get(alert_id)

    def snapshot_path(self, alert_id: str) -> Path | None:
        return self.root / alert_id / "snapshot.jpg" if self.get(alert_id) else None

    def purge_expired(self, now: float) -> int:
        cutoff = now - self.retention_days * 86400
        with self._lock:
            old = [i for i, e in self._alerts.items() if e.ts < cutoff]
            for i in old:
                del self._alerts[i]
        for i in old:
            shutil.rmtree(self.root / i, ignore_errors=True)
        return len(old)
