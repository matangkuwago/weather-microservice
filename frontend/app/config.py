from datetime import date, timedelta
from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # Backend URL of the weather microservice
    BACKEND_URL: str = "http://backend:8000/v1"

    # Default TTL settings
    TTL_WEATHER_DATA: int = 60
    TTL_LOCATIONS: int = 600

    # Used to display default date range selection in the UI
    DEFAULT_DISPLAY_DAYS: int = 30

    # Dynamic fields calculated on the fly
    @computed_field
    @property
    def DEFAULT_END_DATE(self) -> date:
        return date.today()

    @computed_field
    @property
    def DEFAULT_START_DATE(self) -> date:
        return self.DEFAULT_END_DATE - timedelta(days=self.DEFAULT_DISPLAY_DAYS)

    # IQR related defaults
    IQR_MIN: float = 1.0
    IQR_MAX: float = 4.0
    IQR_DEFAULT_VALUE: float = 1.5
    IQR_STEP: float = 0.1

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
