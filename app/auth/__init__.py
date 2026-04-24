"""Magic-link auth (D1.4).

Public surface:

* :class:`AuthService` — request magic links, verify tokens. Wraps the DB
  session factory and an email backend.
* :class:`EmailBackend` / :class:`ConsoleEmailBackend` — pluggable transport.
  Phase 1 ships only the console backend (logs the link). Real SMTP lands
  when we have a mailer.
* :func:`require_user`, :func:`get_current_user` — FastAPI dependencies that
  read the signed-cookie session and resolve it to a :class:`UserRow`.
* :data:`router` — FastAPI router with /auth/request, /auth/verify,
  /auth/logout, /auth/me.

Sessions are signed cookies (``starlette.middleware.sessions``). The app
wires the middleware in :mod:`app.main` with a secret from settings.
"""

from app.auth.deps import (
    AuthError,
    get_current_user,
    require_user,
    require_user_web,
)
from app.auth.email import (
    ConsoleEmailBackend,
    EmailBackend,
    RecordingEmailBackend,
    make_email_backend,
)
from app.auth.router import router
from app.auth.service import (
    AuthService,
    TokenExpiredError,
    TokenInvalidError,
    TokenReusedError,
)

__all__ = [
    "AuthError",
    "AuthService",
    "ConsoleEmailBackend",
    "EmailBackend",
    "RecordingEmailBackend",
    "TokenExpiredError",
    "TokenInvalidError",
    "TokenReusedError",
    "get_current_user",
    "make_email_backend",
    "require_user",
    "require_user_web",
    "router",
]
