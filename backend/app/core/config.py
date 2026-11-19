"""Application settings, loaded from the environment (.env in development)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_debug: bool = True

    database_url: str = (
        "postgresql+psycopg2://simplesight:simplesight@localhost:5432/simplesight"
    )
    redis_url: str = "redis://localhost:6379/0"

    # Auth / JWT. Override JWT_SECRET in every real environment.
    jwt_secret: str = "dev-only-change-me-please-set-a-real-32B+-secret"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 12 * 60


settings = Settings()
