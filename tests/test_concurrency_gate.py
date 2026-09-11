"""Tests for supervisor.concurrency_gate."""

import asyncio
import pytest
from supervisor.concurrency_gate import ConcurrencyGate


def test_concurrency_gate_default_value():
    gate = ConcurrencyGate()
    assert gate.max_concurrent == 3


def test_concurrency_gate_invalid_param():
    with pytest.raises(ValueError, match="at least 1"):
        ConcurrencyGate(max_concurrent=0)


def test_concurrency_gate_limits_active_tasks_at_any_given_moment():
    """Mandatory acceptance test:

    Submit 10 dummy tasks, max_concurrent=3, and assert that at NO POINT during
    execution does the number of actively running tasks exceed 3.
    Also verify peak_active == 3 and all tasks complete successfully.
    """
    async def run_test():
        gate = ConcurrencyGate(max_concurrent=3)
        current_active = 0
        peak_active = 0
        completed = 0
        lock = asyncio.Lock()

        async def dummy_task(task_id: int) -> int:
            nonlocal current_active, peak_active, completed
            async with lock:
                current_active += 1
                if current_active > peak_active:
                    peak_active = current_active
                # Strict invariant: never more than 3 active tasks
                assert current_active <= 3

            # Simulate network I/O work
            await asyncio.sleep(0.04)

            async with lock:
                current_active -= 1
                completed += 1
            return task_id

        # Submit 10 tasks all at once
        tasks = [gate.run(dummy_task(i)) for i in range(10)]
        results = await asyncio.gather(*tasks)

        assert results == list(range(10))
        assert completed == 10
        assert peak_active == 3
        assert current_active == 0

    asyncio.run(run_test())


def test_concurrency_gate_exception_releases_semaphore():
    async def run_test():
        gate = ConcurrencyGate(max_concurrent=1)

        async def failing_task():
            await asyncio.sleep(0.01)
            raise ValueError("Task failed")

        async def succeeding_task():
            await asyncio.sleep(0.01)
            return "ok"

        with pytest.raises(ValueError, match="Task failed"):
            await gate.run(failing_task())

        # Ensure semaphore was released so next task proceeds normally
        res = await gate.run(succeeding_task())
        assert res == "ok"

    asyncio.run(run_test())
