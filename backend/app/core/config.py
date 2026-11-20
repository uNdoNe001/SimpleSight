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

    # Job queue. queue_eager runs tasks inline (no Redis/worker) — handy for local dev.
    collection_queue: str = "collection"
    queue_eager: bool = False

    # Secrets-at-rest encryption (Fernet key: url-safe base64, 32 bytes).
    # This dev default is intentionally weak and must be overridden in every real
    # environment — rotating it makes existing stored secrets undecryptable.
    secrets_encryption_key: str = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
    # Env fallback for provider keys: SECRET_ENV_PREFIX + <NAME uppercased>.
    secret_env_prefix: str = "SIMPLESIGHT_SECRET_"


settings = Settings()
