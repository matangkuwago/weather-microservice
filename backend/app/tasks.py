import asyncio
import logging
from datetime import datetime, date, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db, WeatherData
from app.config import PREDEFINED_LOCATIONS, settings
from app.open_meteo import fetch_multi_location_weather

logger = logging.getLogger("weather-worker")


async def sync_weather_data():
    """
    Optimized background task decoupled from main web execution.
    - Purges records older than configured rolling history days.
    - Automatically builds a uniform batch timeline target dynamically.
    - Sleeps based on configured intervals.
    """
    while True:
        logger.info("Initializing batched background data sync...")

        db: Session = next(get_db())
        try:
            today = date.today()
            history_delta = timedelta(days=settings.SYNC_HISTORY_DAYS)
            cutoff_datetime = datetime.combine(
                today - history_delta, datetime.min.time())

            # 1. Database Housekeeping: Delete records older than the cutoff threshold
            deleted_rows = db.query(WeatherData).filter(
                WeatherData.timestamp < cutoff_datetime).delete()
            if deleted_rows > 0:
                logger.warning(
                    f"Purged {deleted_rows} historical records older than {settings.SYNC_HISTORY_DAYS} days.")
            db.commit()

            # 2. Determine target search window bounds across the system
            oldest_saved_timestamp = db.query(
                func.min(WeatherData.timestamp)).scalar()

            if oldest_saved_timestamp:
                start_fetch_date = oldest_saved_timestamp.date()
            else:
                logger.info(
                    f"Database is empty. Fetching initial {settings.SYNC_HISTORY_DAYS} days historical data buffer.")
                start_fetch_date = today - history_delta

            end_fetch_date = today

            if start_fetch_date <= end_fetch_date:
                logger.info(
                    f"Executing batch update from {start_fetch_date} to {end_fetch_date} for all cities.")

                loc_ids = list(PREDEFINED_LOCATIONS.keys())
                coord_list = [(PREDEFINED_LOCATIONS[lid]["lat"],
                               PREDEFINED_LOCATIONS[lid]["lon"]) for lid in loc_ids]

                batch_api_data = await fetch_multi_location_weather(
                    coord_list, str(start_fetch_date), str(end_fetch_date)
                )

                # 3. Map positional payloads back onto database rows
                inserted_count = 0
                for loc_id, location_points in zip(loc_ids, batch_api_data):
                    for item in location_points:
                        exists = db.query(WeatherData).filter(
                            WeatherData.location_id == loc_id,
                            WeatherData.timestamp == item.timestamp
                        ).first()

                        if not exists:
                            new_record = WeatherData(
                                location_id=loc_id,
                                timestamp=item.timestamp,
                                wind_speed=item.wind_speed,
                                radiation=item.radiation
                            )
                            db.add(new_record)
                            inserted_count += 1
                            logging.info(
                                f"New record added: {loc_id}, {item.timestamp}")

                db.commit()
                logger.info(
                    f"Microservice sync cycle complete. Saved {inserted_count} new hourly data points to SQLite.")

        except asyncio.CancelledError:
            logger.info(
                "Worker execution loop explicitly caught cancellation signal.")
            raise
        except Exception as e:
            logger.error(
                f"Error during batched background loop execution: {e}", exc_info=True)
            db.rollback()
        finally:
            db.close()

        logger.info(
            f"Worker sleeping for {settings.SYNC_INTERVAL_SECONDS} seconds until next scheduled execution.")
        await asyncio.sleep(settings.SYNC_INTERVAL_SECONDS)
