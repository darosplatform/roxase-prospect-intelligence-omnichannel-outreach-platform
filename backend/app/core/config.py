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

    # Secure fetcher (C2 discovery). All connections are validated against
    # network_safety before any byte is sent; these bound the worst case once
    # a connection is allowed.
    discovery_fetch_connect_timeout: float = 5.0
    discovery_fetch_read_timeout: float = 10.0
    discovery_fetch_total_timeout: float = 20.0
    discovery_fetch_max_redirects: int = 5
    discovery_fetch_max_bytes: int = 5_000_000
    discovery_fetch_user_agent: str = "ROXASE-Discovery/1.0 (+https://roxase.invalid/bot)"

    # CORS. Comma-separated origins, or "*" for any origin (the default,
    # safe only because auth is Bearer-token, not cookie-based, and
    # allow_credentials is never enabled — no ambient credential can be
    # exfiltrated via a wildcard origin). Production must set an explicit
    # allowlist instead; enforced by validate_production below.
    cors_allowed_origins: str = "*"

    # Real email provider (SMTP). If smtp_host is unset, the registry falls
    # back to MockEmailProvider — nothing changes for local/dev/test/CI.
    # DRY_RUN and the outreach_enabled kill switch still gate every send
    # regardless of whether a real provider is configured.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_from_name: str | None = None
    smtp_use_tls: bool = True
    smtp_timeout_seconds: int = 10

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

    @property
    def cors_origins_list(self) -> list[str]:
        if self.cors_allowed_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


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
    if settings.cors_allowed_origins.strip() == "*":
        problems.append("cors_allowed_origins must be an explicit allowlist, not '*'")
    if not settings.dry_run and not settings.smtp_host:
        # Disabling dry_run without a real provider configured doesn't fail
        # loudly at send time -- the registry silently falls back to
        # MockEmailProvider, which reports every send as a fabricated
        # success. That's exactly the "conclusion without evidence" failure
        # mode this system exists to prevent, so it's refused at boot.
        problems.append(
            "dry_run is False but smtp_host is unset — email would silently "
            "use MockEmailProvider instead of really sending"
        )
    if problems:
        raise RuntimeError("Insecure production configuration: " + "; ".join(problems))


settings = Settings()
