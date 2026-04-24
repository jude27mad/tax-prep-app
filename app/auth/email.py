"""Pluggable email backends for magic-link delivery.

Phase 1 ships only two backends:

* :class:`ConsoleEmailBackend` — prints the link to a logger. Default in dev
  and CI. Exercised by the smoke test that captures log output.
* :class:`RecordingEmailBackend` — collects sent messages in memory. Tests
  use this to assert the service called us with the right link.

Real SMTP/transactional providers land when Phase 2 needs them. The
interface is intentionally thin so the service layer doesn't care which
transport we use.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

_LOGGER = logging.getLogger("tax_app.auth.email")


class EmailBackend(ABC):
    """Minimal backend contract: deliver a magic-link email."""

    @abstractmethod
    async def send_magic_link(self, to: str, link: str) -> None: ...


class ConsoleEmailBackend(EmailBackend):
    """Log-only backend. Used as the default so the app works zero-config."""

    async def send_magic_link(self, to: str, link: str) -> None:
        _LOGGER.info("magic-link send: to=%s link=%s", to, link)


@dataclass
class _SentMessage:
    to: str
    link: str


@dataclass
class RecordingEmailBackend(EmailBackend):
    """Stores every call in :attr:`sent` for test assertions.

    Tests should prefer this over poking at log output — it gives a typed
    message list without coupling to the logging module.
    """

    sent: list[_SentMessage] = field(default_factory=list)

    async def send_magic_link(self, to: str, link: str) -> None:
        self.sent.append(_SentMessage(to=to, link=link))

    def pop_latest(self) -> _SentMessage:
        return self.sent.pop()


def make_email_backend(kind: str) -> EmailBackend:
    """Build a backend from a settings string ("console" for now).

    We raise instead of silently falling back so a typo in configuration
    doesn't turn into silently-dropped login emails in prod.
    """
    if kind == "console":
        return ConsoleEmailBackend()
    raise ValueError(
        f"Unknown auth_email_backend: {kind!r}. Supported: 'console'."
    )
