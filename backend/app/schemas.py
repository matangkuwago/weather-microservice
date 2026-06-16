from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List


PREDEFINED_LOCATIONS = {
    "mnl": {"name": "Manila", "lat": 14.5995, "lon": 120.9842},
    "tk": {"name": "Tokyo", "lat": 35.6762, "lon": 139.6503},
    "ny": {"name": "New York", "lat": 40.7128, "lon": -74.0060},
}


class AllowedLocations(str, Enum):
    manila = "mnl"
    tokyo = "tk"
    new_york = "ny"


class WeatherDataPoint(BaseModel):
    timestamp: datetime
    wind_speed: float
    radiation: float


class LocationMetaData(BaseModel):
    id: str = Field(...,
                    description="Unique short code string identifier (e.g., 'mnl')")
    name: str = Field(..., description="Full human-readable display name of the city (e.g., 'Manila')")


class LocationListResponse(BaseModel):
    locations: List[LocationMetaData] = Field(
        ..., description="Array containing all supported metadata locations")
