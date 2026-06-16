from enum import Enum
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Number of days of historical data to keep tracked in local SQLite
    SYNC_HISTORY_DAYS: int = 30

    # Frequency of background execution checks in seconds.
    # As per https://github.com/open-meteo/open-data/blob/main/README.md,
    # historical data gets updated every 24 hours.
    SYNC_INTERVAL_SECONDS: int = 86400

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
