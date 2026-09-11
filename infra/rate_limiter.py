"""Sliding Window Rate Limiter for LLM Providers.

Implements Token Bucket / Leaky Bucket inspired Sliding Window Rate Limiting (RFC 6585)
to proactively throttle outgoing requests and prevent 429 RateLimitErrors on free-tier APIs.

Pure Python, zero third-party dependencies, fully testable with mock time.
"""

import asyncio
import logging
import time
from collections import deque
from typing import Callable

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """Sliding-window rate limiter tracking both requests (RPM) and tokens (TPM).

    Thread/coroutine safe via asyncio.Lock.
    """

    def __init__(
        self,
        *,
        max_rpm: int | None = None,
        max_tpm: int | None = None,
        window_seconds: float = 60.0,
        time_func: Callable[[], float] = time.time,
    ) -> None:
        if max_rpm is not None and max_rpm < 1:
            raise ValueError("max_rpm must be at least 1")
        if max_tpm is not None and max_tpm < 1:
            raise ValueError("max_tpm must be at least 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")

        self.max_rpm = max_rpm
        self.max_tpm = max_tpm
        self.window_seconds = window_seconds
        self._time_func = time_func

        self._lock = asyncio.Lock()
        # Deque of (timestamp, token_count)
        self._history: deque[tuple[float, int]] = deque()

    def _cleanup_expired(self, now: float) -> None:
        """Purge entries older than current sliding window."""
        cutoff = now - self.window_seconds
        while self._history and self._history[0][0] <= cutoff:
            self._history.popleft()

    def get_current_usage(self) -> tuple[int, int]:
        """Return (current_rpm, current_tpm) in active sliding window."""
        now = self._time_func()
        self._cleanup_expired(now)
        current_rpm = len(self._history)
        current_tpm = sum(t for _, t in self._history)
        return current_rpm, current_tpm

    async def acquire(self, estimated_tokens: int = 500) -> float:
        """Acquire capacity for an outgoing request, waiting if necessary.

        Args:
            estimated_tokens: Conservative estimate of prompt + expected output tokens.

        Returns:
            float: Total seconds waited before capacity was acquired.
        """
        total_waited = 0.0

        while True:
            async with self._lock:
                now = self._time_func()
                self._cleanup_expired(now)

                current_rpm = len(self._history)
                current_tpm = sum(t for _, t in self._history)

                wait_reasons = []
                delay = 0.0

                # Check RPM limit
                if self.max_rpm is not None and current_rpm >= self.max_rpm:
                    oldest_time = self._history[0][0]
                    rpm_delay = max(0.01, oldest_time + self.window_seconds - now + 0.05)
                    delay = max(delay, rpm_delay)
                    wait_reasons.append(f"RPM cap ({current_rpm}/{self.max_rpm})")

                # Check TPM limit
                if (
                    self.max_tpm is not None
                    and self._history
                    and (current_tpm + estimated_tokens > self.max_tpm)
                ):
                    oldest_time = self._history[0][0]
                    tpm_delay = max(0.01, oldest_time + self.window_seconds - now + 0.05)
                    delay = max(delay, tpm_delay)
                    wait_reasons.append(
                        f"TPM cap ({current_tpm + estimated_tokens}/{self.max_tpm})"
                    )

                if delay <= 0.0:
                    # Capacity granted
                    self._history.append((now, estimated_tokens))
                    return total_waited

            # Capacity not available: log and wait outside the lock to let other coroutines inspect state
            logger.info(
                "Proactive rate pacing: waiting %.2fs due to %s",
                delay,
                ", ".join(wait_reasons),
            )
            await asyncio.sleep(delay)
            total_waited += delay

    def record_usage(self, *, estimated_tokens: int, actual_tokens: int) -> None:
        """Update recent token count with actual tokens reported by LLM provider."""
        delta = actual_tokens - estimated_tokens
        if delta == 0 or not self._history:
            return

        now = self._time_func()
        self._cleanup_expired(now)
        if self._history:
            ts, tokens = self._history[-1]
            adjusted = max(0, tokens + delta)
            self._history[-1] = (ts, adjusted)
