from enum import Enum
from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import List, Optional


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


class WeatherQueryParams(BaseModel):
    location_id: AllowedLocations = Field(
        ..., description="Location Id")
    start_date: date = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: date = Field(..., description="End date (YYYY-MM-DD)")


class LocationMeta(BaseModel):
    id: str = Field(...,
                    description="Unique short code string identifier (e.g., 'mnl')")
    name: str = Field(..., description="Full human-readable display name of the city (e.g., 'Manila')")
    # made optional so the /v1/locations endpoint doesn't have to emit coordinates if it doesn't want to
    latitude: Optional[float] = Field(
        None, description="Latitude coordinate center bound")
    longitude: Optional[float] = Field(
        None, description="Longitude coordinate center bound")


class LocationListResponse(BaseModel):
    locations: List[LocationMeta] = Field(
        ..., description="Array containing all supported metadata locations")


class WeatherResponse(BaseModel):
    location: LocationMeta = Field(...,
                                   description="The location details for this dataset")
    data: List[WeatherDataPoint] = Field(...,
                                         description="Array of sorted hourly metrics")


class AnomalyPoint(BaseModel):
    timestamp: datetime
    value: float
    bound_limit: float


class AnomalyResponse(BaseModel):
    """Uses composition to attach the unified location metadata block to anomaly data."""
    location: LocationMeta = Field(...,
                                   description="The location details for this dataset")
    method: str = "IQR"
    wind_speed_anomalies: List[AnomalyPoint]
    radiation_anomalies: List[AnomalyPoint]
