"""D1.7 — rate limiter unit tests.

Driven directly (no FastAPI) so we control the clock and can assert the
sliding-window arithmetic without timing flakiness. The HTTP integration
is exercised in :mod:`tests.unit.test_auth_router_rate_limit`.
"""

from __future__ import annotations

import pytest

from app.auth.rate_limit import (
    AuthRequestRateLimiter,
    RateLimiter,
)


# ---------------------------------------------------------------------------
# RateLimiter primitive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_allows_under_limit() -> None:
    limiter = RateLimiter(limit=3, window_seconds=60)
    for i in range(3):
        result = await limiter.check("k", now=100.0 + i)
        assert result.allowed is True
        assert result.retry_after == 0


@pytest.mark.asyncio
async def test_denies_over_limit_with_retry_after() -> None:
    limiter = RateLimiter(limit=2, window_seconds=60)
    await limiter.check("k", now=100.0)
    await limiter.check("k", now=110.0)
    blocked = await limiter.check("k", now=120.0)
    assert blocked.allowed is False
    # Oldest hit was at 100; expires at 160. now=120 → retry in ~40s.
    assert 35 <= blocked.retry_after <= 45


@pytest.mark.asyncio
async def test_window_slides() -> None:
    limiter = RateLimiter(limit=2, window_seconds=60)
    await limiter.check("k", now=100.0)
    await limiter.check("k", now=110.0)
    # After the window passes, hits age out.
    fresh = await limiter.check("k", now=200.0)
    assert fresh.allowed is True


@pytest.mark.asyncio
async def test_keys_are_isolated() -> None:
    limiter = RateLimiter(limit=1, window_seconds=60)
    a = await limiter.check("alice", now=100.0)
    b = await limiter.check("bob", now=100.0)
    assert a.allowed is True
    assert b.allowed is True
    blocked_a = await limiter.check("alice", now=101.0)
    assert blocked_a.allowed is False


@pytest.mark.asyncio
async def test_denied_attempt_does_not_extend_window() -> None:
    """Hammering after being blocked must not push the oldest-hit forward."""
    limiter = RateLimiter(limit=1, window_seconds=60)
    await limiter.check("k", now=100.0)
    for offset in range(5):
        denied = await limiter.check("k", now=110.0 + offset)
        assert denied.allowed is False
    # The original window expires at 160 regardless of intermediate denials.
    fresh = await limiter.check("k", now=161.0)
    assert fresh.allowed is True


def test_rejects_invalid_construction() -> None:
    with pytest.raises(ValueError):
        RateLimiter(limit=0, window_seconds=60)
    with pytest.raises(ValueError):
        RateLimiter(limit=1, window_seconds=0)


# ---------------------------------------------------------------------------
# AuthRequestRateLimiter (per-email + per-IP composite)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_composite_allows_when_both_under_limit() -> None:
    composite = AuthRequestRateLimiter(
        per_email=RateLimiter(limit=3, window_seconds=60),
        per_ip=RateLimiter(limit=3, window_seconds=60),
    )
    result = await composite.check(email="a@example.com", ip="1.1.1.1")
    assert result.allowed is True


@pytest.mark.asyncio
async def test_composite_blocks_when_per_email_exceeded() -> None:
    composite = AuthRequestRateLimiter(
        per_email=RateLimiter(limit=1, window_seconds=60),
        per_ip=RateLimiter(limit=10, window_seconds=60),
    )
    await composite.check(email="a@example.com", ip="1.1.1.1")
    blocked = await composite.check(email="a@example.com", ip="2.2.2.2")
    assert blocked.allowed is False


@pytest.mark.asyncio
async def test_composite_blocks_when_per_ip_exceeded_across_emails() -> None:
    """Single IP rotating emails must still trip the per-IP cap."""
    composite = AuthRequestRateLimiter(
        per_email=RateLimiter(limit=10, window_seconds=60),
        per_ip=RateLimiter(limit=2, window_seconds=60),
    )
    await composite.check(email="a@example.com", ip="1.1.1.1")
    await composite.check(email="b@example.com", ip="1.1.1.1")
    blocked = await composite.check(email="c@example.com", ip="1.1.1.1")
    assert blocked.allowed is False


@pytest.mark.asyncio
async def test_composite_normalizes_email_case() -> None:
    composite = AuthRequestRateLimiter(
        per_email=RateLimiter(limit=1, window_seconds=60),
        per_ip=RateLimiter(limit=10, window_seconds=60),
    )
    await composite.check(email="Alice@Example.com", ip="1.1.1.1")
    blocked = await composite.check(email="alice@example.com", ip="2.2.2.2")
    assert blocked.allowed is False
