"""In-memory sliding-window rate limiter for the magic-link request route.

The limiter answers one question: "has this key been hit more than ``limit``
times in the last ``window`` seconds?" — and gives back a ``retry_after``
hint when the answer is yes.

Why in-memory:

* The whole magic-link flow is best-effort already (a transient SMTP failure
  is silently swallowed). A worker restart resetting the limiter window is
  acceptable.
* No new infra dependency. Redis can replace the storage when we go
  multi-worker; the public surface (``check`` / ``RateLimitResult``) stays
  the same.

Why two limits (per-email + per-IP):

* Per-email caps the obvious mailbombing of one inbox.
* Per-IP caps drive-by enumeration from a single source. Without this an
  attacker who rotates emails per request can issue arbitrarily many
  links from one host before each individual email tips the per-email
  cap.

Concurrency: an :class:`asyncio.Lock` serializes mutations of the deque
storage. The expected QPS on /auth/request is single-digit, so contention
is not a concern.
"""

from __future__ import annotations

import time
from asyncio import Lock
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitResult:
    """Outcome of a single :meth:`RateLimiter.check` call.

    ``allowed`` is False when the caller is over the cap. ``retry_after``
    is the number of seconds the caller should wait before the oldest
    counted hit ages out — clamped to a non-negative integer so it can
    feed straight into the HTTP ``Retry-After`` header.
    """

    allowed: bool
    retry_after: int


class RateLimiter:
    """Sliding-window counter keyed by arbitrary strings.

    Construct one limiter per (limit, window) pair — typically one for
    per-email and one for per-IP. The two limiters share no state, so
    they can be checked independently.
    """

    def __init__(self, *, limit: int, window_seconds: float) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._limit = limit
        self._window = float(window_seconds)
        self._buckets: dict[str, deque[float]] = {}
        self._lock = Lock()

    async def check(self, key: str, *, now: float | None = None) -> RateLimitResult:
        """Record an attempt for ``key`` and decide whether to allow it.

        Side-effect: when allowed, this appends the current timestamp to
        the bucket. When denied, the bucket is left untouched so over-cap
        callers can't extend their own window by hammering us.
        """
        current = time.monotonic() if now is None else now
        cutoff = current - self._window

        async with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = deque()
                self._buckets[key] = bucket

            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= self._limit:
                # The oldest hit dictates how long until a slot frees up.
                retry_after = max(1, int(bucket[0] + self._window - current) + 1)
                return RateLimitResult(allowed=False, retry_after=retry_after)

            bucket.append(current)
            return RateLimitResult(allowed=True, retry_after=0)

    def reset(self) -> None:
        """Clear all counters. Tests use this between cases."""
        self._buckets.clear()


@dataclass
class AuthRequestRateLimiter:
    """Bundle of per-email + per-IP limiters wired for /auth/request.

    Both must allow the request for it to proceed. We surface the larger
    ``retry_after`` so the caller knows the longest wait until any limit
    frees.
    """

    per_email: RateLimiter
    per_ip: RateLimiter

    async def check(self, *, email: str, ip: str) -> RateLimitResult:
        normalized_email = email.strip().lower()
        # The IP-only check goes first so a flood of bad emails from one
        # source still trips the per-IP cap even if each email is unique
        # and would otherwise sail past the per-email check.
        ip_result = await self.per_ip.check(normalized_email if not ip else ip)
        email_result = await self.per_email.check(normalized_email)

        if ip_result.allowed and email_result.allowed:
            return RateLimitResult(allowed=True, retry_after=0)

        retry_after = max(ip_result.retry_after, email_result.retry_after)
        return RateLimitResult(allowed=False, retry_after=retry_after)

    def reset(self) -> None:
        self.per_email.reset()
        self.per_ip.reset()
