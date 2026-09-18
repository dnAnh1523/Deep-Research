"""Concurrency Gate managing parallel coroutines.

Enforces throughput boundaries (defaulting to N=3 to balance speed and upstream API rate limits)
via asyncio.Semaphore. Allows callers to submit any number of tasks simultaneously
while strictly throttling concurrent active execution.
"""

import asyncio
from typing import Awaitable, TypeVar

T = TypeVar("T")


class ConcurrencyGate:
    """Limits concurrent coroutine execution using an internal asyncio.Semaphore.

    Supervisor submits all N researcher tasks at once (e.g., via asyncio.gather);
    the gate manages throughput internally so no more than max_concurrent coroutines
    execute simultaneously.
    """

    def __init__(self, *, max_concurrent: int = 3) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1")
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def run(self, coro: Awaitable[T]) -> T:
        """Execute coroutine bounded by the semaphore."""
        async with self._semaphore:
            return await coro
