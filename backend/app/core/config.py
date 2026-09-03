from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "APP_", "env_file": ".env", "env_file_encoding": "utf-8"}

    env: str = "local"
    version: str = "0.1.0"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://roxase:roxase@localhost:5432/roxase"
    redis_url: str = "redis://localhost:6379/0"

    model_config = {
        "env_prefix": "",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
