import asyncio
import logging

from datetime import datetime, date, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db, WeatherData
from app.config import settings
from app.open_meteo import fetch_multi_location_weather
from app.schemas import PREDEFINED_LOCATIONS, WeatherDataPoint


logger = logging.getLogger("weather-tasks")


def _chunk_locations(locations_dict: dict, max_locations: int):
    """Yields locations not exceeding max_locations."""
    items = list(locations_dict.items())
    for i in range(0, len(items), max_locations):
        yield dict(items[i:i + max_locations])


def _chunk_date_range(start_date: datetime, end_date: datetime, max_days: int):
    """Yields tuple intervals of (start_date, end_date) not exceeding max_days."""
    current_start = start_date
    while current_start <= end_date:
        current_end = min(
            current_start + timedelta(days=max_days - 1), end_date)
        yield current_start, current_end
        current_start = current_end + timedelta(days=1)


def _save_batch_data(location_ids: List[str], batch_api_data: List[List[WeatherDataPoint]], db: Session):
    """Bulk-inserts historical weather metrics for multiple locations."""

    inserted_count = 0

    # Collect all new records in memory first, then add them in bulk
    new_records = []

    for loc_id, location_points in zip(location_ids, batch_api_data):
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
                new_records.append(new_record)
                inserted_count += 1

    if new_records:
        db.add_all(new_records)
        db.commit()
    else:
        logger.info("No new data to insert.")

    return inserted_count


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
            history_delta = timedelta(days=settings.SYNC_HISTORY_DAYS - 1)
            cutoff_datetime = datetime.combine(
                today - history_delta, datetime.min.time())

            # Clean up stale entries older than your sliding history window
            # Using delete() with filter is efficient in SQLAlchemy
            deleted_rows = db.query(WeatherData).filter(
                WeatherData.timestamp < cutoff_datetime).delete(synchronize_session=False)
            if deleted_rows > 0:
                logger.warning(
                    f"Purged {deleted_rows} historical records older than {settings.SYNC_HISTORY_DAYS} days.")
            db.commit()

            # Check the newest entry in the database to find the sync starting point
            latest_saved_timestamp = db.query(
                func.max(WeatherData.timestamp)).scalar()

            if latest_saved_timestamp:
                start_fetch_date = latest_saved_timestamp.date()
            else:
                start_fetch_date = today - history_delta

            end_fetch_date = today

            total_inserted = 0

            for chunk_start, chunk_end in _chunk_date_range(start_fetch_date, end_fetch_date, settings.DAYS_CHUNK_SIZE):
                for locations in _chunk_locations(PREDEFINED_LOCATIONS, settings.LOCATION_CHUNK_SIZE):

                    if chunk_start <= chunk_end:
                        location_names = ", ".join(
                            [v["name"] for v in locations.values()])
                        logger.info(
                            f"Syncing gaps: Fetching data from {chunk_start} to {chunk_end} for locations {location_names}.")

                        location_ids = list(locations.keys())
                        coord_list = [(locations[lid]["lat"],
                                       locations[lid]["lon"]) for lid in location_ids]

                        batch_api_data = await fetch_multi_location_weather(
                            coord_list, str(chunk_start), str(chunk_end)
                        )

                        total_inserted += _save_batch_data(
                            location_ids, batch_api_data, db)

            logger.info(
                f"Sync complete. Total number of records inserted: {total_inserted}.")

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
