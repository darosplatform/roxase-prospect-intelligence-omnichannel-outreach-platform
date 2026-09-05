"""Production hardening tests: secrets validation, rate limiter, pool config,
backup script, JSON logging switch."""

import os
from pathlib import Path

import pytest

from app.core.config import Settings, validate_production
from app.core.limits import RateLimiter


class _FakeRedis:
    """In-memory INCR/EXPIRE stand-in for rate limiter tests."""

    def __init__(self):
        self.data: dict[str, int] = {}
        self.ttl: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.data[key] = self.data.get(key, 0) + 1
        return self.data[key]

    async def expire(self, key: str, ttl: int) -> None:
        self.ttl[key] = ttl


class _FakeRequest:
    class _State:
        user = None

    def __init__(self, host="1.2.3.4"):
        client = type("Client", (), {"host": host})()
        self.client = client
        self.state = self._State()


def test_production_rejects_demo_secret():
    s = Settings(
        env="production",
        jwt_secret_key="change-me-in-production-use-openssl-rand-hex-32",
        database_url="postgresql+asyncpg://x",
        rate_limit_enabled=True,
    )
    with pytest.raises(RuntimeError):
        validate_production(s)


def test_production_rejects_weak_secret():
    s = Settings(env="production", jwt_secret_key="short", database_url="x")
    with pytest.raises(RuntimeError):
        validate_production(s)


def test_production_accepts_strong_secure_config():
    s = Settings(
        env="production",
        jwt_secret_key="L" * 48,
        database_url="postgresql+asyncpg://host/db",
        rate_limit_enabled=True,
        cors_allowed_origins="https://app.roxase.example",
    )
    validate_production(s)


def test_production_rejects_wildcard_cors():
    s = Settings(
        env="production",
        jwt_secret_key="L" * 48,
        database_url="postgresql+asyncpg://host/db",
        rate_limit_enabled=True,
        cors_allowed_origins="*",
    )
    with pytest.raises(RuntimeError):
        validate_production(s)


def test_cors_origins_list_parses_comma_separated():
    s = Settings(cors_allowed_origins="https://a.example, https://b.example")
    assert s.cors_origins_list == ["https://a.example", "https://b.example"]


def test_cors_origins_list_wildcard():
    s = Settings(cors_allowed_origins="*")
    assert s.cors_origins_list == ["*"]


def test_local_is_not_gated():
    s = Settings(env="local", jwt_secret_key="demo")
    validate_production(s)


@pytest.mark.asyncio
async def test_rate_limiter_block_after_limit(monkeypatch):
    fake = _FakeRedis()
    # Force get_redis() to return the fake so no real network is touched.
    monkeypatch.setattr("app.core.cache.redis_client", fake)
    limiter = RateLimiter(limit=2, window_seconds=5, scope="auth")

    req = _FakeRequest()
    await limiter(req)  # 1
    await limiter(req)  # 2
    with pytest.raises(Exception) as exc:
        await limiter(req)  # 3 -> HTTP 429
    assert getattr(exc.value, "status_code", None) == 429


@pytest.mark.asyncio
async def test_rate_limiter_disabled_when_config_off(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr("app.core.cache.redis_client", fake)
    monkeypatch.setattr("app.core.limits.settings.rate_limit_enabled", False)
    limiter = RateLimiter(limit=1, window_seconds=5, scope="x")

    req = _FakeRequest()
    await limiter(req)
    await limiter(req)  # would exceed, but disabled -> no error
    assert True


def test_db_pool_settings_exposed():
    s = Settings(db_pool_size=5, db_max_overflow=7, db_pool_timeout=9)
    assert s.db_pool_size == 5
    assert s.db_max_overflow == 7
    assert s.db_pool_timeout == 9


def test_backup_script_exists_and_is_executable():
    script = Path(__file__).resolve().parents[2] / "scripts" / "backup.sh"
    assert script.exists()
    assert os.access(script, os.X_OK)
    text = script.read_text()
    assert "pg_dump" in text
    assert "DB_NAME" in text


def test_gitignore_ignores_backups():
    gitignore = Path(__file__).resolve().parents[2] / ".gitignore"
    assert "backups/" in gitignore.read_text()


def test_env_example_has_hardening_options():
    env = Path(__file__).resolve().parents[2] / ".env.example"
    assert env.exists()
    text = env.read_text()
    for key in ("db_pool_size", "rate_limit_enabled", "log_json", "worker_lease_seconds"):
        assert key in text


def test_json_logging_flag_parse():
    from app.core.logging_config import configure_logging

    # JSON formatter path should not raise for either mode.
    configure_logging(log_json=True)
    configure_logging(log_json=False)