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

    model_config = {
        "env_prefix": "",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
