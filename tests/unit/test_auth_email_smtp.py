"""D1.7 — SMTP email backend unit tests.

We don't stand up a real MTA. Instead we verify:

* The factory wires console / smtp / unknown backends correctly.
* :class:`SmtpEmailBackend` builds a valid RFC-822 message and hands the
  expected kwargs to ``aiosmtplib.send``.
* Transport errors get wrapped as :class:`SmtpSendError` so the router's
  blanket ``except Exception`` catches them under a typed alias.
* Mutually-exclusive TLS modes are rejected at construction time.
"""

from __future__ import annotations

from email.message import EmailMessage
from typing import Any

import pytest

from app.auth.email import (
    ConsoleEmailBackend,
    SmtpConfig,
    SmtpEmailBackend,
    SmtpSendError,
    make_email_backend,
)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_factory_returns_console_for_default() -> None:
    backend = make_email_backend("console")
    assert isinstance(backend, ConsoleEmailBackend)


def test_factory_returns_smtp_when_configured() -> None:
    config = SmtpConfig(host="mail.example", from_address="bot@example")
    backend = make_email_backend("smtp", smtp_config=config)
    assert isinstance(backend, SmtpEmailBackend)


def test_factory_smtp_without_config_raises() -> None:
    with pytest.raises(ValueError, match="requires smtp_config"):
        make_email_backend("smtp")


def test_factory_unknown_backend_raises() -> None:
    with pytest.raises(ValueError, match="Unknown auth_email_backend"):
        make_email_backend("aws-ses")


# ---------------------------------------------------------------------------
# SmtpEmailBackend
# ---------------------------------------------------------------------------


def test_smtp_backend_rejects_both_tls_modes() -> None:
    config = SmtpConfig(
        host="mail.example",
        from_address="bot@example",
        use_tls=True,
        use_ssl=True,
    )
    with pytest.raises(ValueError, match="mutually exclusive"):
        SmtpEmailBackend(config)


@pytest.mark.asyncio
async def test_smtp_backend_sends_message_with_expected_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_send(message: EmailMessage, **kwargs: Any) -> None:
        captured["message"] = message
        captured["kwargs"] = kwargs

    fake_module = type("FakeAiosmtplib", (), {"send": staticmethod(fake_send)})
    monkeypatch.setitem(__import__("sys").modules, "aiosmtplib", fake_module)

    config = SmtpConfig(
        host="mail.example.com",
        port=587,
        username="apikey",
        password="secret",
        from_address="auth@example.com",
        use_tls=True,
        use_ssl=False,
        timeout=7.5,
        subject="Sign in to Tax App",
    )
    backend = SmtpEmailBackend(config)
    await backend.send_magic_link("user@example.com", "https://app/auth/verify?token=abc")

    msg: EmailMessage = captured["message"]
    assert msg["From"] == "auth@example.com"
    assert msg["To"] == "user@example.com"
    assert msg["Subject"] == "Sign in to Tax App"
    body = msg.get_content()
    assert "https://app/auth/verify?token=abc" in body
    assert "expires shortly" in body  # phrasing from the template

    kwargs = captured["kwargs"]
    assert kwargs["hostname"] == "mail.example.com"
    assert kwargs["port"] == 587
    assert kwargs["username"] == "apikey"
    assert kwargs["password"] == "secret"
    assert kwargs["start_tls"] is True
    assert kwargs["use_tls"] is False
    assert kwargs["timeout"] == 7.5


@pytest.mark.asyncio
async def test_smtp_backend_wraps_transport_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_send(*args: Any, **kwargs: Any) -> None:
        raise OSError("connection refused")

    fake_module = type("FakeAiosmtplib", (), {"send": staticmethod(fake_send)})
    monkeypatch.setitem(__import__("sys").modules, "aiosmtplib", fake_module)

    config = SmtpConfig(host="mail.example", from_address="bot@example")
    backend = SmtpEmailBackend(config)

    with pytest.raises(SmtpSendError, match="Failed to send magic link"):
        await backend.send_magic_link("user@example.com", "https://app/x")


@pytest.mark.asyncio
async def test_smtp_backend_wraps_missing_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If aiosmtplib isn't installed the backend should fail with a clear error."""
    import sys

    monkeypatch.setitem(sys.modules, "aiosmtplib", None)  # forces ImportError

    config = SmtpConfig(host="mail.example", from_address="bot@example")
    backend = SmtpEmailBackend(config)

    with pytest.raises(SmtpSendError, match="aiosmtplib is required"):
        await backend.send_magic_link("user@example.com", "https://app/x")
