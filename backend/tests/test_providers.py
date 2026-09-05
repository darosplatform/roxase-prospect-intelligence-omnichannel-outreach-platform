"""SmtpEmailProvider and provider-registry selection tests.

No real network/SMTP connection is ever made here: smtplib.SMTP /
SMTP_SSL are replaced with an in-memory fake that records what would have
been sent, the same style already used for the secure fetcher tests.
"""

import smtplib
import uuid

import pytest

from app.core.config import Settings, validate_production
from app.services.providers import (
    Message,
    MockEmailProvider,
    ProviderRegistry,
    SmtpEmailProvider,
    _default_email_provider,
)


class _FakeSmtp:
    """Stand-in for smtplib.SMTP / SMTP_SSL used as a context manager."""

    instances: list["_FakeSmtp"] = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_args = None
        self.sent_message = None
        _FakeSmtp.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, email_msg):
        self.sent_message = email_msg


class _FailingSmtp(_FakeSmtp):
    def __enter__(self):
        raise smtplib.SMTPConnectError(421, "connection refused")


def _message(**overrides):
    base = dict(
        id=uuid.uuid4(),
        channel="email",
        to="lead@example.com",
        subject="Hello",
        body="Body text",
    )
    base.update(overrides)
    return Message(**base)


@pytest.fixture(autouse=True)
def _reset_fake_smtp():
    _FakeSmtp.instances = []
    yield
    _FakeSmtp.instances = []


@pytest.mark.asyncio
async def test_smtp_provider_sends_via_starttls_on_587(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _FakeSmtp)
    provider = SmtpEmailProvider(
        host="smtp.example.com",
        port=587,
        from_email="outreach@example.com",
        username="user",
        password="pass",
        use_tls=True,
    )
    result = await provider.send(_message())

    assert result.ok is True
    assert result.provider_message_id
    sent = _FakeSmtp.instances[0]
    assert sent.host == "smtp.example.com"
    assert sent.started_tls is True
    assert sent.login_args == ("user", "pass")
    assert sent.sent_message["To"] == "lead@example.com"
    assert sent.sent_message["Subject"] == "Hello"
    assert sent.sent_message.get_content().strip() == "Body text"


@pytest.mark.asyncio
async def test_smtp_provider_uses_implicit_tls_on_465(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSmtp)
    provider = SmtpEmailProvider(host="smtp.example.com", port=465, from_email="a@b.com")
    result = await provider.send(_message())

    assert result.ok is True
    sent = _FakeSmtp.instances[0]
    assert sent.started_tls is False  # implicit TLS: no separate STARTTLS call


@pytest.mark.asyncio
async def test_smtp_provider_skips_login_without_credentials(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _FakeSmtp)
    provider = SmtpEmailProvider(host="smtp.example.com", port=587, from_email="a@b.com")
    await provider.send(_message())

    assert _FakeSmtp.instances[0].login_args is None


@pytest.mark.asyncio
async def test_smtp_provider_reports_failure_without_raising(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _FailingSmtp)
    provider = SmtpEmailProvider(host="smtp.example.com", port=587, from_email="a@b.com")
    result = await provider.send(_message())

    assert result.ok is False
    assert "connection refused" in result.error


@pytest.mark.asyncio
async def test_default_email_provider_is_mock_when_smtp_unconfigured(monkeypatch):
    monkeypatch.setattr("app.services.providers.settings.smtp_host", None)
    provider = _default_email_provider()
    assert isinstance(provider, MockEmailProvider)


@pytest.mark.asyncio
async def test_default_email_provider_is_smtp_when_configured(monkeypatch):
    monkeypatch.setattr("app.services.providers.settings.smtp_host", "smtp.example.com")
    monkeypatch.setattr("app.services.providers.settings.smtp_from_email", "outreach@example.com")
    provider = _default_email_provider()
    assert isinstance(provider, SmtpEmailProvider)
    assert provider.host == "smtp.example.com"


def test_provider_registry_still_defaults_email_to_mock_by_default():
    registry = ProviderRegistry()
    assert isinstance(registry.get("email"), MockEmailProvider)


def test_production_rejects_dry_run_false_without_smtp():
    s = Settings(
        env="production",
        jwt_secret_key="L" * 48,
        database_url="postgresql+asyncpg://host/db",
        rate_limit_enabled=True,
        cors_allowed_origins="https://app.roxase.example",
        dry_run=False,
    )
    with pytest.raises(RuntimeError, match="smtp_host"):
        validate_production(s)


def test_production_accepts_dry_run_false_with_smtp_configured():
    s = Settings(
        env="production",
        jwt_secret_key="L" * 48,
        database_url="postgresql+asyncpg://host/db",
        rate_limit_enabled=True,
        cors_allowed_origins="https://app.roxase.example",
        dry_run=False,
        smtp_host="smtp.example.com",
    )
    validate_production(s)
