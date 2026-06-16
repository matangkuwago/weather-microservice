import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from app.database import engine, Base, get_db
from app.tasks import sync_weather_data
from app.schemas import (
    PREDEFINED_LOCATIONS,
    LocationMetaData,
    LocationListResponse,
    WeatherQueryParams,
    WeatherResponse,
    WeatherDataPoint
)
from app.services import get_cached_weather


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


@app.get("/v1/locations", response_model=LocationListResponse)
async def get_supported_locations():
    """Retrieves all static supported locations with their respective string IDs and display names."""
    meta_list = [
        LocationMetaData(id=loc_id, name=details["name"])
        for loc_id, details in PREDEFINED_LOCATIONS.items()
    ]
    return LocationListResponse(locations=meta_list)


@app.get("/v1/weather-data", response_model=WeatherResponse)
async def get_weather(params: WeatherQueryParams = Depends(), db: Session = Depends(get_db)):
    location, records = await get_cached_weather(params, db)
    data_points = [WeatherDataPoint(
        timestamp=r.timestamp, wind_speed=r.wind_speed, radiation=r.radiation) for r in records]

    return WeatherResponse(
        location_id=location["location_id"],
        location=location["name"],
        latitude=location["latitude"],
        longitude=location["longitude"],
        data=data_points
    )
