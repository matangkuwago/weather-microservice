from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Number of days of historical data to keep tracked in local SQLite
    SYNC_HISTORY_DAYS: int = 30

    # Frequency of background execution checks in seconds.
    # As per https://github.com/open-meteo/open-data/blob/main/README.md,
    # historical data gets updated every 24 hours.
    SYNC_INTERVAL_SECONDS: int = 86400

    # AI chat agent settings
    AI_PROVIDER: Literal["ollama", "openai", "anthropic"] = "ollama"
    OLLAMA_MODEL: str = "qwen3.5:9b"
    OPENAI_MODEL: str = "gpt-4o"
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    AI_TEMPERATURE: float = 0

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
