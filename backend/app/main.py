import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.database import engine, Base
from app.tasks import sync_weather_data

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("weather-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP LOGIC ---
    logger.info("Application booting up. Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database schemas confirmed active.")

    # spawn task that downloads weather data
    sync_task = asyncio.create_task(sync_weather_data())

    yield  # API serves live requests here

    # --- SHUTDOWN LOGIC ---
    logger.warning(
        "Application shutting down. Signaling worker thread cancellation...")
    sync_task.cancel()
    try:
        await sync_task
    except (asyncio.CancelledError, Exception) as e:
        if not isinstance(e, asyncio.CancelledError):
            logger.critical(
                f"Sync worker caught an unexpected fault during framework teardown: {e}", exc_info=True)
    finally:
        logger.info("Background synchronization worker shutdown cleanly.")

app = FastAPI(title="Weather Data Microservice",
              version="0.0.1", lifespan=lifespan)

# TODO: Add GET data endpoints below
