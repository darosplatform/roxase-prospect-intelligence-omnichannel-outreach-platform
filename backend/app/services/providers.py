"""Provider adapters.

Every channel exposes a common `async send(message) -> ProviderResult`
interface. Email has a real adapter (SmtpEmailProvider); WhatsApp, Telegram
and Meta are still stubs (NoopProvider) pending their own credentials/sandbox.
A Mock adapter is provided for tests and is also the default for "email"
until SMTP is actually configured (see `_default_email_provider` below).

A provider NEVER decides whether to send — it only executes a message that the
Policy Engine has already approved, and only once DRY_RUN and the kill switch
have both already cleared it (see `services/outbox.py::process_request`).
"""

import asyncio
import smtplib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.message import EmailMessage

from app.core.config import settings


@dataclass
class Message:
    id: uuid.UUID
    channel: str
    to: str
    subject: str | None = None
    body: str = ""
    template_id: uuid.UUID | None = None
    tenant_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ProviderResult:
    ok: bool
    provider_message_id: str | None = None
    error: str | None = None
    sent_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class Provider:
    """Common interface implemented by every channel adapter."""

    channel: str = ""

    async def send(self, message: Message) -> ProviderResult:  # pragma: no cover
        raise NotImplementedError


class MockEmailProvider(Provider):
    """Deterministic email provider for tests / dry nature."""

    channel = "email"

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls: list[Message] = []

    async def send(self, message: Message) -> ProviderResult:
        self.calls.append(message)
        if self.fail:
            return ProviderResult(ok=False, error="mock provider failure")
        return ProviderResult(ok=True, provider_message_id=str(message.id))


class NoopProvider(Provider):
    """Placeholder used when a channel has no real integration yet."""

    def __init__(self, channel: str = "*"):
        self.channel = channel

    async def send(self, message: Message) -> ProviderResult:  # pragma: no cover
        # Never reached in a real flow once adapters are wired.
        return ProviderResult(ok=False, error="no provider configured")


class SmtpEmailProvider(Provider):
    """Sends real email over SMTP (STARTTLS on the usual 587, or implicit
    TLS when configured on 465). Runs the blocking smtplib call in a worker
    thread so it never stalls the event loop.
    """

    channel = "email"

    def __init__(
        self,
        host: str,
        port: int,
        from_email: str,
        username: str | None = None,
        password: str | None = None,
        from_name: str | None = None,
        use_tls: bool = True,
        timeout: int = 10,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.from_name = from_name
        self.use_tls = use_tls
        self.timeout = timeout

    def _build_message(self, message: Message) -> EmailMessage:
        email_msg = EmailMessage()
        email_msg["Subject"] = message.subject or ""
        email_msg["From"] = (
            f"{self.from_name} <{self.from_email}>" if self.from_name else self.from_email
        )
        email_msg["To"] = message.to
        email_msg["Message-ID"] = f"<{message.id}@roxase>"
        email_msg.set_content(message.body)
        return email_msg

    def _send_sync(self, message: Message) -> ProviderResult:
        email_msg = self._build_message(message)
        try:
            smtp_cls = smtplib.SMTP_SSL if self.port == 465 else smtplib.SMTP
            with smtp_cls(self.host, self.port, timeout=self.timeout) as smtp:
                if self.use_tls and self.port != 465:
                    smtp.starttls()
                if self.username and self.password:
                    smtp.login(self.username, self.password)
                smtp.send_message(email_msg)
            return ProviderResult(ok=True, provider_message_id=email_msg["Message-ID"])
        except (smtplib.SMTPException, OSError) as exc:
            return ProviderResult(ok=False, error=str(exc))

    async def send(self, message: Message) -> ProviderResult:
        return await asyncio.to_thread(self._send_sync, message)


def _default_email_provider() -> Provider:
    if settings.smtp_host:
        return SmtpEmailProvider(
            host=settings.smtp_host,
            port=settings.smtp_port,
            from_email=settings.smtp_from_email or f"noreply@{settings.smtp_host}",
            username=settings.smtp_username,
            password=settings.smtp_password,
            from_name=settings.smtp_from_name,
            use_tls=settings.smtp_use_tls,
            timeout=settings.smtp_timeout_seconds,
        )
    return MockEmailProvider()


class ProviderRegistry:
    """Maps a channel name to a provider instance."""

    def __init__(self, providers: dict[str, Provider] | None = None):
        self._providers: dict[str, Provider] = dict(providers or {})
        self._providers.setdefault("email", _default_email_provider())
        for ch in ("whatsapp", "telegram", "messenger", "instagram"):
            self._providers.setdefault(ch, NoopProvider(ch))

    def get(self, channel: str) -> Provider:
        return self._providers.get(channel, NoopProvider(channel))

    def provider_for(self, channel: str) -> Provider:
        return self.get(channel)

    def register(self, channel: str, provider: Provider) -> None:
        self._providers[channel] = provider


registry = ProviderRegistry()