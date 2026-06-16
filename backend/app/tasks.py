import asyncio
import logging
from datetime import datetime, date, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db, WeatherData
from app.config import settings
from app.open_meteo import fetch_multi_location_weather
from app.schemas import PREDEFINED_LOCATIONS


logger = logging.getLogger("weather-worker")


async def sync_weather_data():
    """
    Background worker that runs every hour. It is responsible for finding data gaps
    in SQLite and downloading incremental updates to keep the cache full.
    """
    while True:
        logger.info("Starting background weather data gap analysis...")

        db: Session = next(get_db())
        try:
            today = date.today()
            history_delta = timedelta(days=settings.SYNC_HISTORY_DAYS)
            cutoff_datetime = datetime.combine(
                today - history_delta, datetime.min.time())

            # 1. Clean up stale entries older than your sliding history window (e.g., 30 days)
            deleted_rows = db.query(WeatherData).filter(
                WeatherData.timestamp < cutoff_datetime).delete()
            if deleted_rows > 0:
                logger.warning(
                    f"Purged {deleted_rows} historical records older than {settings.SYNC_HISTORY_DAYS} days.")
            db.commit()

            # 2. Check the newest entry in the database to find the sync starting point
            # This ensures that if the service is down for days, it catches up automatically on boot
            latest_saved_timestamp = db.query(
                func.max(WeatherData.timestamp)).scalar()

            if latest_saved_timestamp:
                # Start fetching from the day of the latest recorded data point
                start_fetch_date = latest_saved_timestamp.date()
            else:
                # If the database is completely empty, pull the full historical window
                start_fetch_date = today - history_delta

            end_fetch_date = today

            # 3. Trigger a single batched network call if updates are required
            if start_fetch_date <= end_fetch_date:
                logger.info(
                    f"Syncing gaps: Fetching data from {start_fetch_date} to {end_fetch_date} for all cities.")

                loc_ids = list(PREDEFINED_LOCATIONS.keys())
                coord_list = [(PREDEFINED_LOCATIONS[lid]["lat"],
                               PREDEFINED_LOCATIONS[lid]["lon"]) for lid in loc_ids]

                # Fetch clean, linear-interpolated data blocks
                batch_api_data = await fetch_multi_location_weather(
                    coord_list, str(start_fetch_date), str(end_fetch_date)
                )

                # 4. Save missing hourly entries
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

                db.commit()
                logger.info(
                    f"Sync task complete. Successfully filled {inserted_count} missing hours into SQLite.")

        except asyncio.CancelledError:
            logger.info("Sync worker received a shutdown cancellation signal.")
            raise
        except Exception as e:
            logger.error(
                f"Error encountered during background sync execution: {e}", exc_info=True)
            db.rollback()
        finally:
            db.close()

        logger.info(
            f"Sync worker sleeping for {settings.SYNC_INTERVAL_SECONDS} seconds.")
        await asyncio.sleep(settings.SYNC_INTERVAL_SECONDS)
