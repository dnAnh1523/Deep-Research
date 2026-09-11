"""F.I.R.S.T Unit tests for SlidingWindowRateLimiter (infra/rate_limiter.py)."""

import asyncio
import pytest
from infra.rate_limiter import SlidingWindowRateLimiter


class MockClock:
    """Mock clock for deterministic, instantaneous time manipulation in tests."""

    def __init__(self, initial_time: float = 1000.0) -> None:
        self.current_time = initial_time

    def time(self) -> float:
        return self.current_time

    def advance(self, seconds: float) -> None:
        self.current_time += seconds


def test_acquire_immediate_within_limits() -> None:
    async def _test() -> None:
        clock = MockClock()
        limiter = SlidingWindowRateLimiter(
            max_rpm=10, max_tpm=5000, window_seconds=60.0, time_func=clock.time
        )

        waited = await limiter.acquire(estimated_tokens=500)
        assert waited == 0.0

        rpm, tpm = limiter.get_current_usage()
        assert rpm == 1
        assert tpm == 500

    asyncio.run(_test())


def test_rpm_limit_throttling() -> None:
    async def _test() -> None:
        clock = MockClock()
        limiter = SlidingWindowRateLimiter(
            max_rpm=2, max_tpm=10000, window_seconds=60.0, time_func=clock.time
        )

        # 2 requests succeed immediately
        assert await limiter.acquire(estimated_tokens=100) == 0.0
        assert await limiter.acquire(estimated_tokens=100) == 0.0

        rpm, _ = limiter.get_current_usage()
        assert rpm == 2

        # Advance clock past window
        clock.advance(61.0)
        rpm, _ = limiter.get_current_usage()
        assert rpm == 0

        # Next request succeeds immediately again
        assert await limiter.acquire(estimated_tokens=100) == 0.0

    asyncio.run(_test())


def test_tpm_limit_throttling() -> None:
    async def _test() -> None:
        clock = MockClock()
        limiter = SlidingWindowRateLimiter(
            max_rpm=10, max_tpm=1500, window_seconds=60.0, time_func=clock.time
        )

        # First request uses 1000 tokens
        assert await limiter.acquire(estimated_tokens=1000) == 0.0

        # Second request of 800 tokens exceeds 1500 limit
        # Advance clock by 61s so capacity recovers
        clock.advance(61.0)
        assert await limiter.acquire(estimated_tokens=800) == 0.0

    asyncio.run(_test())


def test_record_usage_adjusts_delta() -> None:
    clock = MockClock()
    limiter = SlidingWindowRateLimiter(
        max_rpm=10, max_tpm=5000, window_seconds=60.0, time_func=clock.time
    )

    asyncio.run(limiter.acquire(estimated_tokens=500))
    _, tpm = limiter.get_current_usage()
    assert tpm == 500

    # LLM actual usage was 750 tokens
    limiter.record_usage(estimated_tokens=500, actual_tokens=750)
    _, tpm = limiter.get_current_usage()
    assert tpm == 750


def test_invalid_parameters_raise_error() -> None:
    with pytest.raises(ValueError, match="max_rpm must be at least 1"):
        SlidingWindowRateLimiter(max_rpm=0)

    with pytest.raises(ValueError, match="max_tpm must be at least 1"):
        SlidingWindowRateLimiter(max_tpm=0)

    with pytest.raises(ValueError, match="window_seconds must be positive"):
        SlidingWindowRateLimiter(window_seconds=0)
