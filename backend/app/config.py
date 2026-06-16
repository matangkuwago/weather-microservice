from enum import Enum
from pydantic_settings import BaseSettings, SettingsConfigDict


class AllowedLocations(str, Enum):
    new_york = "ny"
    tokyo = "tk"
    london = "ldn"


PREDEFINED_LOCATIONS = {
    "ny": {"name": "New York", "lat": 40.7128, "lon": -74.0060},
    "tk": {"name": "Tokyo", "lat": 35.6762, "lon": 139.6503},
    "ldn": {"name": "London", "lat": 51.5074, "lon": -0.1278},
}


class Settings(BaseSettings):
    # Number of days of historical data to keep tracked in local SQLite
    SYNC_HISTORY_DAYS: int = 2

    # Frequency of background execution checks in seconds (3600 seconds = 1 hour)
    SYNC_INTERVAL_SECONDS: int = 3600

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
