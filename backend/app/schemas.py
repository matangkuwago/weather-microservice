from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


PREDEFINED_LOCATIONS = {
    "mnl": {"name": "Manila", "lat": 14.5995, "lon": 120.9842},
    "tk": {"name": "Tokyo", "lat": 35.6762, "lon": 139.6503},
    "ny": {"name": "New York", "lat": 40.7128, "lon": -74.0060},
}


class WeatherDataPoint(BaseModel):
    timestamp: datetime
    wind_speed: float
    radiation: float


class WeatherQueryParams(BaseModel):
    location_id: str = Field(...,
                             description="The location's unique short identifier")
    start_date: date = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: date = Field(..., description="End date (YYYY-MM-DD)")

    @field_validator("location_id")
    @classmethod
    def validate_location_id(cls, value: str) -> str:
        """Runtime validator to ensure the location exists in our master dictionary."""
        normalized_value = value.strip().lower()

        if normalized_value not in PREDEFINED_LOCATIONS:
            allowed_keys = ", ".join(
                f"'{k}'" for k in PREDEFINED_LOCATIONS.keys())
            raise ValueError(
                f"Invalid location_id '{value}'. Must be one of: {allowed_keys}"
            )

        return normalized_value


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


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


class WeatherSummary(BaseModel):
    location: str
    location_id: str
    analysis_period: dict
    summary: dict
    hourly_data: List[dict]


class AnomalyReport(BaseModel):
    location: str
    location_id: str
    analysis_period: dict
    method: str
    summary: dict
    wind_speed_anomalies: List[dict]
    radiation_anomalies: List[dict]


class ToolError(BaseModel):
    error: str
