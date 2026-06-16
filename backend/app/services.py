from datetime import datetime, time
from sqlalchemy.orm import Session
from typing import List, Tuple

from app.database import WeatherData
from app.schemas import PREDEFINED_LOCATIONS
from app.schemas import WeatherQueryParams


async def get_cached_weather(
    params: WeatherQueryParams,
    db: Session
) -> Tuple[dict, List[WeatherData]]:
    """
    Pure cache-read service. Queries the local SQLite database instantly.
    Contains zero external network fallback code.
    """
    loc_id = params.location_id.value
    coords = PREDEFINED_LOCATIONS[loc_id]

    start_dt = datetime.combine(params.start_date, time.min)
    end_dt = datetime.combine(params.end_date, time.max)

    # Query local database directly
    records = db.query(WeatherData).filter(
        WeatherData.location_id == loc_id,
        WeatherData.timestamp >= start_dt,
        WeatherData.timestamp <= end_dt
    ).order_by(WeatherData.timestamp).all()

    location_meta = {
        "location_id": loc_id,
        "name": coords["name"],
        "latitude": coords["lat"],
        "longitude": coords["lon"]
    }

    return location_meta, records
