import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.alerts import AlertService, AlertStore
from app.api.events import router as events_router
from app.api.zones import router as zones_router
from app.behavior import ZonesError, load_zones, make_engine
from app.config import Settings
from app.detection.yolo import YoloDetector
from app.events import EventBus
from app.pipeline import Pipeline
from app.sources import make_source
from app.tracking import PersonTracker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

PURGE_INTERVAL_S = 3600.0


async def purge_periodically(store: AlertStore) -> None:
    while True:
        await asyncio.sleep(PURGE_INTERVAL_S)
        try:
            await asyncio.to_thread(store.purge_expired, time.time())
        except Exception:
            log.exception("alert purge failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = Settings()
    bus = app.state.bus = EventBus()
    bus.bind(asyncio.get_running_loop())
    source = app.state.source = make_source(cfg.camera_id, cfg.source_url)
    source.start()
    try:
        store = AlertStore(cfg.alerts_dir, cfg.alert_retention_days)
        store.purge_expired(time.time())
    except (OSError, ValueError) as e:
        log.error("alerts disabled, cannot use ALERTS_DIR %r: %s", cfg.alerts_dir, e)
        store = None
    app.state.alert_store = store
    app.state.zones = []
    pipeline = None
    engine = None
    service = None
    try:
        zones = load_zones(cfg.zones_path)
        app.state.zones = zones.get(cfg.camera_id, [])
        engine = make_engine(cfg.camera_id, app.state.zones)
        service = AlertService(store, bus, zones) if store else None
        if not any(z.dwell_s for z in app.state.zones):
            log.warning("no dwell_s zone for %s: dwell alerts can never fire", cfg.camera_id)
    except ZonesError as e:
        log.error("behavior rules disabled: %s", e)
    if cfg.detector == "yolo":
        pipeline = app.state.pipeline = Pipeline(
            source,
            lambda: YoloDetector(cfg),
            PersonTracker(cfg.inference_fps, cfg.track_conf),
            bus,
            cfg.camera_id,
            cfg.inference_fps,
            on_alert=lambda a: log.info("ALERT %s", a),
            engine=engine,
            alert_sink=service.handle if service else None,
        )
        pipeline.start()

    async def log_stats():
        while True:
            await asyncio.sleep(1)
            log.info("stats %s", source.stats())

    tasks = [asyncio.create_task(log_stats())]
    if store:
        tasks.append(asyncio.create_task(purge_periodically(store)))
    yield
    for task in tasks:
        task.cancel()
    if pipeline:
        await asyncio.to_thread(pipeline.stop)
    await asyncio.to_thread(source.stop)


app = FastAPI(lifespan=lifespan)
app.include_router(events_router)
app.include_router(zones_router)
