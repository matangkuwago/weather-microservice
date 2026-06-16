import logging
import httpx

from fastapi import HTTPException
from typing import List, Tuple

from app.schemas import WeatherDataPoint


logger = logging.getLogger("weather-sync")


def interpolate_series(values: List[float | None]) -> List[float]:
    """
    Fills gaps (None values) in a numerical series using linear interpolation.
    - Handles leading/trailing None values safely by edge-clipping.
    - Mathematically fills middle gaps based on surrounding points.
    """
    n = len(values)
    if n == 0:
        return []

    clean_values = list(values)

    if all(v is None for v in clean_values):
        return [0.0] * n

    first_valid = next(v for v in clean_values if v is not None)
    for i in range(n):
        if clean_values[i] is not None:
            break
        clean_values[i] = first_valid

    last_valid = next(clean_values[i] for i in range(
        n - 1, -1, -1) if clean_values[i] is not None)
    for i in range(n - 1, -1, -1):
        if clean_values[i] is not None:
            break
        clean_values[i] = last_valid

    i = 0
    while i < n:
        if clean_values[i] is None:
            gap_start = i - 1
            while i < n and clean_values[i] is None:
                i += 1
            gap_end = i

            y0 = clean_values[gap_start]
            y1 = clean_values[gap_end]
            gap_length = gap_end - gap_start

            for k in range(gap_start + 1, gap_end):
                fraction = (k - gap_start) / gap_length
                clean_values[k] = y0 + fraction * (y1 - y0)
        else:
            i += 1

    return [float(v) for v in clean_values]


async def fetch_multi_location_weather(
    coordinates: List[Tuple[float, float]],
    start: str,
    end: str
) -> List[List[WeatherDataPoint]]:
    """
    Fetches weather data using native asynchronous HTTP JSON mapping.
    Fixes the matching parameter list bug for Open-Meteo multi-location array requests.
    """
    if not coordinates:
        return []

    # Format coordinates into comma-separated strings
    latitudes = ",".join(str(lat) for lat, _ in coordinates)
    longitudes = ",".join(str(lon) for _, lon in coordinates)

    # Multiply the start and end dates to match the number of locations.
    # For 3 locations, "2026-06-01" becomes "2026-06-01,2026-06-01,2026-06-01"
    num_locations = len(coordinates)
    start_dates_array = ",".join([start] * num_locations)
    end_dates_array = ",".join([end] * num_locations)

    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": latitudes,
        "longitude": longitudes,
        "start_date": start_dates_array,  # Fixed parameter
        "end_date": end_dates_array,      # Fixed parameter
        "hourly": "wind_speed_10m,shortwave_radiation",
        "wind_speed_unit": "kmh",
        "timezone": "UTC"
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, params=params)

        # Defensive check: Log the raw payload if the server fails so we can catch it before crashing
        if response.status_code != 200:
            logger.error(
                f"Open-Meteo API returned error status: {response.status_code}. Server dump: {response.text}")
            raise HTTPException(
                status_code=502, detail="Error batch fetching data from Open-Meteo")

        try:
            raw_data = response.json()
        except Exception:
            logger.critical(
                f"JSON Parsing failed! Raw content was: {response.text}")
            raise HTTPException(
                status_code=502, detail="Open-Meteo response could not be parsed as JSON.")

        # Open-Meteo returns a single dict if 1 location is queried,
        # or an explicit LIST of dicts if multiple coordinates are passed.
        results = raw_data if isinstance(raw_data, list) else [raw_data]

        batch_output = []
        for index, location_node in enumerate(results):
            hourly = location_node.get("hourly", {})
            times = hourly.get("time", [])
            winds = hourly.get("wind_speed_10m", [])
            rads = hourly.get("shortwave_radiation", [])

            if not (len(times) == len(winds) == len(rads)):
                logger.error(
                    f"Mismatched array lengths received for coordinate index {index}")
                continue

            if None in winds:
                logger.warning(
                    f"Gaps identified in wind speeds for location index {index}. Interpolating...")
                winds = interpolate_series(winds)
            if None in rads:
                logger.warning(
                    f"Gaps identified in solar radiation for location index {index}. Interpolating...")
                rads = interpolate_series(rads)

            normalized_location_points = []

            for t, w, r in zip(times, winds, rads):
                w = max(0.0, float(w))
                r = max(0.0, float(r))

                if w > 450.0:
                    logger.error(
                        f"Unrealistic wind speed peak intercepted ({w} km/h) at {t}. Clipping.")
                    w = 450.0
                if r > 1400.0:
                    logger.error(
                        f"Unrealistic solar radiation spike intercepted ({r} W/m²) at {t}. Clipping.")
                    r = 1400.0

                normalized_location_points.append(
                    WeatherDataPoint(timestamp=t, wind_speed=w, radiation=r)
                )

            batch_output.append(normalized_location_points)

        return batch_output
