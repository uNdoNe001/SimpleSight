"""Application settings, loaded from the environment (.env in development)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_debug: bool = True

    database_url: str = "postgresql://simplesight:simplesight@localhost:5432/simplesight"
    redis_url: str = "redis://localhost:6379/0"


settings = Settings()
