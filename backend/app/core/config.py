from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    env: str = "local"
    version: str = "0.1.0"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://roxase:roxase@localhost:5432/roxase"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # Global outreach kill switch. Independent from any provider/DAROS.
    # When False, real sends are blocked; dry-run simulation is still allowed.
    outreach_enabled: bool = True

    # Sticky dry-run guard. When True, NO real external send may ever occur:
    # providers are not contacted and a simulated result is recorded. Kept True
    # by default; only disabled explicitly per deployment for a real channel.
    dry_run: bool = True

    # Outbox worker.
    worker_enabled: bool = True
    worker_poll_interval: float = 1.0
    worker_batch_size: int = 50
    worker_lease_seconds: int = 60
    worker_max_attempts: int = 5
    worker_base_backoff: float = 2.0
    worker_max_backoff: float = 600.0

    # Observability / hardening.
    log_json: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    rate_limit_enabled: bool = True
    rate_limit_rps: int = 100
    rate_limit_burst: int = 200
    rate_limit_window: int = 5

    model_config = {
        "env_prefix": "",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


_EXAMPLE_JWT = "change-me-in-production-use-openssl-rand-hex-32"


def validate_production(settings: "Settings") -> None:
    """Hard fail on insecure config when running in a production env.

    Deliberately raises instead of warn-falling-back: ROXASE must never silently
    run with a default/demo secret, unencrypted DB or a kill switch that is off
    expecting real sends.
    """
    if settings.env != "production":
        return
    problems: list[str] = []
    if settings.jwt_secret_key == _EXAMPLE_JWT or len(settings.jwt_secret_key) < 32:
        problems.append("jwt_secret_key must be a strong secret (>=32 chars)")
    if not settings.database_url.startswith("postgresql+asyncpg://"):
        problems.append("database_url must be postgresql+asyncpg (PostgreSQL)")
    if settings.rate_limit_enabled is False:
        problems.append("rate_limit_enabled must be True in production")
    if problems:
        raise RuntimeError("Insecure production configuration: " + "; ".join(problems))


settings = Settings()
