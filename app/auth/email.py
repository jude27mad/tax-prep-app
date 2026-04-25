"""Pluggable email backends for magic-link delivery.

Phase 1 ships three backends:

* :class:`ConsoleEmailBackend` — prints the link to a logger. Default in dev
  and CI. Exercised by the smoke test that captures log output.
* :class:`RecordingEmailBackend` — collects sent messages in memory. Tests
  use this to assert the service called us with the right link.
* :class:`SmtpEmailBackend` — delivers via SMTP/STARTTLS using
  :mod:`aiosmtplib`. Production transport for self-hosted MTAs and
  transactional providers (SendGrid/Postmark/SES/Mailgun) that expose an
  SMTP submission endpoint.

The interface is intentionally thin so the service layer doesn't care which
transport we use. Pick the backend via ``AUTH_EMAIL_BACKEND``.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from email.message import EmailMessage

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


@dataclass(frozen=True)
class SmtpConfig:
    """Connection + envelope settings for :class:`SmtpEmailBackend`.

    ``use_tls`` selects STARTTLS on a plaintext port (typically 587).
    ``use_ssl`` selects implicit TLS on connect (typically 465). They are
    mutually exclusive: enable only one. Set both to ``False`` for plain
    SMTP on port 25 — the backend will warn but not refuse, since some
    internal relays still operate that way.
    """

    host: str
    from_address: str
    port: int = 587
    username: str | None = None
    password: str | None = None
    use_tls: bool = True
    use_ssl: bool = False
    timeout: float = 10.0
    subject: str = "Your sign-in link"


class SmtpSendError(RuntimeError):
    """Raised when SMTP delivery fails. Caller decides whether to swallow.

    The router currently logs and returns 204 either way (oracle-prevention),
    but operators want this distinct from generic exceptions so log filters
    can alert on it.
    """


class SmtpEmailBackend(EmailBackend):
    """Send magic links over SMTP using :mod:`aiosmtplib`.

    The backend builds a minimal text/plain :class:`EmailMessage` containing
    the link and dispatches via ``aiosmtplib.send``. We deliberately do not
    ship an HTML template here — login links work in any client and adding
    HTML would force us to maintain a multipart MIME ladder for the sake
    of looks. Operators who want branded email can layer that on later.

    Failures bubble up as :class:`SmtpSendError`. The router catches and
    logs them so we never tell an attacker whether SMTP was up.
    """

    def __init__(self, config: SmtpConfig) -> None:
        if config.use_tls and config.use_ssl:
            raise ValueError(
                "SMTP backend: use_tls and use_ssl are mutually exclusive. "
                "Pick STARTTLS (use_tls=True) or implicit TLS (use_ssl=True)."
            )
        self._config = config

    async def send_magic_link(self, to: str, link: str) -> None:
        config = self._config
        message = EmailMessage()
        message["From"] = config.from_address
        message["To"] = to
        message["Subject"] = config.subject
        message.set_content(
            "Click the link below to sign in. It expires shortly and can\n"
            "only be used once.\n\n"
            f"{link}\n\n"
            "If you didn't request this, you can ignore this email.\n"
        )

        try:
            # Imported lazily so test envs without aiosmtplib (or callers
            # that only use ConsoleEmailBackend) don't pay the import cost
            # or fail at module load.
            import aiosmtplib
        except ImportError as exc:  # pragma: no cover - dependency check
            raise SmtpSendError(
                "aiosmtplib is required for the SMTP email backend. "
                "Install it with 'pip install aiosmtplib'."
            ) from exc

        try:
            await aiosmtplib.send(
                message,
                hostname=config.host,
                port=config.port,
                username=config.username,
                password=config.password,
                start_tls=config.use_tls,
                use_tls=config.use_ssl,
                timeout=config.timeout,
            )
        except Exception as exc:  # noqa: BLE001 — wrap any transport error uniformly
            raise SmtpSendError(
                f"Failed to send magic link to {to} via {config.host}:{config.port}"
            ) from exc


def make_email_backend(
    kind: str, *, smtp_config: SmtpConfig | None = None
) -> EmailBackend:
    """Build a backend from a settings string.

    Supported kinds: ``"console"`` (default) and ``"smtp"``. We raise
    instead of silently falling back so a typo in configuration doesn't
    turn into silently-dropped login emails in prod.
    """
    if kind == "console":
        return ConsoleEmailBackend()
    if kind == "smtp":
        if smtp_config is None:
            raise ValueError(
                "auth_email_backend='smtp' requires smtp_config. "
                "Set AUTH_SMTP_HOST + AUTH_SMTP_FROM."
            )
        return SmtpEmailBackend(smtp_config)
    raise ValueError(
        f"Unknown auth_email_backend: {kind!r}. Supported: 'console', 'smtp'."
    )
