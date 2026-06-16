from enum import Enum
from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import List


PREDEFINED_LOCATIONS = {
    "ny": {"name": "New York", "lat": 40.7128, "lon": -74.0060},
    "tk": {"name": "Tokyo", "lat": 35.6762, "lon": 139.6503},
    "ldn": {"name": "London", "lat": 51.5074, "lon": -0.1278},
}


class AllowedLocations(str, Enum):
    new_york = "ny"
    tokyo = "tk"
    london = "ldn"


class WeatherDataPoint(BaseModel):
    timestamp: datetime
    wind_speed: float
    radiation: float
