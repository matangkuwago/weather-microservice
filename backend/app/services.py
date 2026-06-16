import logging
import numpy as np

from datetime import datetime, time
from typing import List, Tuple, Dict
from sqlalchemy.orm import Session

from app.database import WeatherData
from app.schemas import (
    PREDEFINED_LOCATIONS,
    WeatherQueryParams,
    WeatherDataPoint,
    AnomalyPoint
)


def get_cached_weather(
    params: WeatherQueryParams,
    db: Session
) -> Tuple[dict, List[WeatherData]]:
    """
    Pure cache-read service. Queries the local SQLite database instantly.
    Contains zero external network fallback code.

    Args:
        params: Query parameters including location_id and date range.
        db: SQLAlchemy session.

    Returns:
        A tuple containing location metadata and a list of weather records.

    Raises:
        KeyError: If the location_id is not found in PREDEFINED_LOCATIONS.
    """

    loc_id = params.location_id
    if loc_id not in PREDEFINED_LOCATIONS:
        raise KeyError(
            f"Location ID {loc_id} not found in predefined locations.")

    coords = PREDEFINED_LOCATIONS[loc_id]

    start_dt = datetime.combine(params.start_date, time.min)
    end_dt = datetime.combine(params.end_date, time.max)
    logging.info(f"Retrieving data for {loc_id=}, {start_dt=}, {end_dt=}")

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


def detect_iqr_anomalies(
        data: List[WeatherDataPoint],
        factor: float = 1.5
) -> Dict[str, List[AnomalyPoint]]:
    """
    Detects anomalies in wind speed and radiation data using the Interquartile Range (IQR) method.

    Logic:
        Lower Bound = Q1 - (factor * IQR)
        Upper Bound = Q3 + (factor * IQR)

    Args:
        data: List of WeatherDataPoint objects.
        factor: Multiplier for the IQR (default 1.5 is standard for mild outliers).

    Returns:
        A dictionary with keys 'wind_speed' and 'radiation', each containing a list of AnomalyPoint.
        Returns empty lists if input data is empty.
    """
    if not data:
        return {"wind_speed": [], "radiation": []}

    wind_speeds = [p.wind_speed for p in data]
    radiations = [p.radiation for p in data]

    def get_bounds(values: List[float]) -> tuple[float, float]:
        q1, q3 = np.percentile(values, [25, 75])
        iqr = q3 - q1
        return q1 - (factor * iqr), q3 + (factor * iqr)

    w_lower, w_upper = get_bounds(wind_speeds)
    r_lower, r_upper = get_bounds(radiations)

    wind_anomalies = []
    radiation_anomalies = []

    for p in data:
        if p.wind_speed < w_lower or p.wind_speed > w_upper:
            limit = w_upper if p.wind_speed > w_upper else w_lower
            wind_anomalies.append(AnomalyPoint(
                timestamp=p.timestamp, value=p.wind_speed, bound_limit=limit))

        if p.radiation < r_lower or p.radiation > r_upper:
            limit = r_upper if p.radiation > r_upper else r_lower
            radiation_anomalies.append(AnomalyPoint(
                timestamp=p.timestamp, value=p.radiation, bound_limit=limit))

    return {"wind_speed": wind_anomalies, "radiation": radiation_anomalies}
