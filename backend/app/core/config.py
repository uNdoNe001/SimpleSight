"""Application settings, loaded from the environment (.env in development)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_debug: bool = True

    database_url: str = (
        "postgresql+psycopg2://simplesight:simplesight@localhost:5432/simplesight"
    )
    # Dev convenience: create tables on startup. Set false in production and manage the
    # schema with Alembic (`alembic upgrade head`) instead.
    auto_create_tables: bool = True
    redis_url: str = "redis://localhost:6379/0"

    # Auth / JWT. Override JWT_SECRET in every real environment.
    jwt_secret: str = "dev-only-change-me-please-set-a-real-32B+-secret"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 12 * 60

    # Job queue. queue_eager runs tasks inline (no Redis/worker) — handy for local dev.
    collection_queue: str = "collection"
    queue_eager: bool = False

    # Per-provider rate limiting (SMPLSGHT-20). Disable only for local experiments.
    rate_limit_enabled: bool = True
    # Backend for the limiter (SMPLSGHT-60): "memory" (single worker) or "redis" (shared across
    # workers). Redis uses an atomic Lua token-bucket under this key prefix.
    rate_limit_backend: str = "memory"
    rate_limit_redis_prefix: str = "simplesight:rl"

    # Dependent second-stage enrichment: subdomain-takeover detection (SMPLSGHT-45).
    # Runs CNAME lookups over discovered subdomains; disable to skip the second DNS pass.
    takeover_detection_enabled: bool = True

    # Continuous monitoring (SMPLSGHT-52): feature gate for the /api/monitoring endpoints.
    monitoring_enabled: bool = True

    # Grounded AI narrative (SMPLSGHT-58). The deterministic template narrator is always used
    # unless a Claude API key is configured AND this is on; even then the model is instructed to
    # summarize only the supplied findings — never to invent. Model id per the Claude 5 family.
    narrative_ai_enabled: bool = True
    narrative_model: str = "claude-haiku-5-5"
    # Secret name under which the tenant's Claude API key is resolved (secrets manager / env).
    narrative_api_key_secret: str = "anthropic_api_key"

    # Secrets-at-rest encryption (Fernet key: url-safe base64, 32 bytes).
    # This dev default is intentionally weak and must be overridden in every real
    # environment — rotating it makes existing stored secrets undecryptable.
    secrets_encryption_key: str = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
    # Env fallback for provider keys: SECRET_ENV_PREFIX + <NAME uppercased>.
    secret_env_prefix: str = "SIMPLESIGHT_SECRET_"


settings = Settings()
