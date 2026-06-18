import logging
import asyncio

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import engine, Base, get_db
from app.tasks import sync_weather_data
from app.schemas import (
    LocationMeta,
    LocationListResponse,
    WeatherQueryParams,
    WeatherResponse,
    WeatherDataPoint,
    AnomalyResponse,
    ChatRequest,
    ChatResponse
)
from app.services import get_cached_weather, detect_iqr_anomalies
from app.agent import get_weather_agent_executor, get_session_history


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
    # Passes directly into the unified LocationMeta class without coordinate padding
    meta_list = [
        LocationMeta(id=loc_id, name=details["name"])
        for loc_id, details in settings.PREDEFINED_LOCATIONS.items()
    ]
    return LocationListResponse(locations=meta_list)


@app.get("/v1/weather-data", response_model=WeatherResponse)
async def get_weather(params: WeatherQueryParams = Depends(), db: Session = Depends(get_db)):
    location, records = get_cached_weather(params, db)
    data_points = [WeatherDataPoint(
        timestamp=r.timestamp, wind_speed=r.wind_speed, radiation=r.radiation) for r in records]

    return WeatherResponse(
        location=LocationMeta(
            id=params.location_id,
            name=location["name"],
            latitude=location["latitude"],
            longitude=location["longitude"]
        ),
        data=data_points
    )


@app.get("/v1/weather-data/anomalies", response_model=AnomalyResponse)
async def get_anomalies(
    params: WeatherQueryParams = Depends(),
    threshold: float = Query(1.5, description="IQR multiplier threshold"),
    db: Session = Depends(get_db)
):
    location, records = get_cached_weather(params, db)
    data_points = [WeatherDataPoint(
        timestamp=r.timestamp, wind_speed=r.wind_speed, radiation=r.radiation) for r in records]

    anomalies = detect_iqr_anomalies(data_points, factor=threshold)

    return AnomalyResponse(
        location=LocationMeta(
            id=params.location_id,
            name=location["name"],
            latitude=location["latitude"],
            longitude=location["longitude"]
        ),
        method=f"IQR (factor: {threshold})",
        wind_speed_anomalies=anomalies["wind_speed"],
        radiation_anomalies=anomalies["radiation"]
    )


@app.post("/v1/chat", response_model=ChatResponse)
def handle_agent_chat(payload: ChatRequest):
    try:
        executor = get_weather_agent_executor()

        # Fetch this specific user's conversational thread
        history_backend = get_session_history(payload.session_id)

        # Invoke the agent, passing the historical messages array
        result = executor.invoke({
            "input": payload.message,
            "chat_history": history_backend.messages
        })

        raw_output = result.get("output", "")

        # Handle newer Anthropic nested response formats natively
        if isinstance(raw_output, list) and len(raw_output) > 0:
            clean_reply = raw_output[0].get("text", str(raw_output)) if isinstance(
                raw_output[0], dict) else str(raw_output)
        elif isinstance(raw_output, dict):
            clean_reply = raw_output.get("text", str(raw_output))
        else:
            clean_reply = str(raw_output)

        # Commit the current turn to memory so the AI remembers it on the next request
        history_backend.add_user_message(payload.message)
        history_backend.add_ai_message(clean_reply)

        return ChatResponse(reply=clean_reply)

    except Exception as e:
        logger.error(f"Chat execution routine blocked: {e}", exc_info=True)
        return ChatResponse(
            reply="The AI agent has encountered a system issue. Please report this issue to the system administrator."
        )
