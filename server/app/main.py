import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.events import router as events_router
from app.config import Settings
from app.events import EventBus
from app.sources import make_source

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = Settings()
    bus = app.state.bus = EventBus()
    bus.bind(asyncio.get_running_loop())
    source = app.state.source = make_source(cfg.camera_id, cfg.source_url)
    source.start()

    async def log_stats():
        while True:
            await asyncio.sleep(1)
            log.info("stats %s", source.stats())

    task = asyncio.create_task(log_stats())
    yield
    task.cancel()
    await asyncio.to_thread(source.stop)


app = FastAPI(lifespan=lifespan)
app.include_router(events_router)
