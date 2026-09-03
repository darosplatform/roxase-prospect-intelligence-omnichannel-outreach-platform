"""Provider adapters.

No real network calls or tokens here. Every channel exposes a common
`send(message) -> ProviderResult` interface. The concrete adapters (Email,
WhatsApp, Telegram, Meta) are stubs; a Mock adapter is provided for tests.

A provider NEVER decides whether to send — it only executes a message that the
Policy Engine has already approved.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


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

    def send(self, message: Message) -> ProviderResult:  # pragma: no cover
        raise NotImplementedError


class MockEmailProvider(Provider):
    """Deterministic email provider for tests / dry nature."""

    channel = "email"

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls: list[Message] = []

    def send(self, message: Message) -> ProviderResult:
        self.calls.append(message)
        if self.fail:
            return ProviderResult(ok=False, error="mock provider failure")
        return ProviderResult(ok=True, provider_message_id=str(message.id))


class NoopProvider(Provider):
    """Placeholder used when a channel has no real integration yet."""

    def __init__(self, channel: str = "*"):
        self.channel = channel

    def send(self, message: Message) -> ProviderResult:  # pragma: no cover
        # Never reached in a real flow once adapters are wired.
        return ProviderResult(ok=False, error="no provider configured")


class ProviderRegistry:
    """Maps a channel name to a provider instance."""

    def __init__(self, providers: dict[str, Provider] | None = None):
        self._providers: dict[str, Provider] = dict(providers or {})
        self._providers.setdefault("email", MockEmailProvider())
        for ch in ("whatsapp", "telegram", "messenger", "instagram"):
            self._providers.setdefault(ch, NoopProvider(ch))

    def get(self, channel: str) -> Provider:
        return self._providers.get(channel, NoopProvider(channel))

    def provider_for(self, channel: str) -> Provider:
        return self.get(channel)

    def register(self, channel: str, provider: Provider) -> None:
        self._providers[channel] = provider


registry = ProviderRegistry()