import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import Settings
from app.sources import make_source

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = Settings()
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
