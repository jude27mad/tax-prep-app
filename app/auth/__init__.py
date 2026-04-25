"""Magic-link auth (D1.4 + D1.7).

Public surface:

* :class:`AuthService` — request magic links, verify tokens. Wraps the DB
  session factory and an email backend.
* :class:`EmailBackend` / :class:`ConsoleEmailBackend` /
  :class:`SmtpEmailBackend` — pluggable transport. Pick via
  ``AUTH_EMAIL_BACKEND`` (``console`` or ``smtp``).
* :func:`require_user`, :func:`get_current_user` — FastAPI dependencies that
  read the signed-cookie session and resolve it to a :class:`UserRow`.
* :class:`AuthRequestRateLimiter` — sliding-window per-email + per-IP cap
  on POST /auth/request. D1.7.
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
    SmtpConfig,
    SmtpEmailBackend,
    SmtpSendError,
    make_email_backend,
)
from app.auth.rate_limit import (
    AuthRequestRateLimiter,
    RateLimiter,
    RateLimitResult,
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
    "AuthRequestRateLimiter",
    "AuthService",
    "ConsoleEmailBackend",
    "EmailBackend",
    "RateLimitResult",
    "RateLimiter",
    "RecordingEmailBackend",
    "SmtpConfig",
    "SmtpEmailBackend",
    "SmtpSendError",
    "TokenExpiredError",
    "TokenInvalidError",
    "TokenReusedError",
    "get_current_user",
    "make_email_backend",
    "require_user",
    "require_user_web",
    "router",
]
