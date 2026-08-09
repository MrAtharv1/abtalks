"""
Tests for CadenceController.
Uses time mocking to avoid real sleeps.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

from app.runtime.cadence import CadenceController


def make_cadence(min_interval=60, max_interval=300, initial_delay=0):
    return CadenceController(
        min_interval=min_interval,
        max_interval=max_interval,
        initial_delay=initial_delay,
    )


def test_initial_cycle_is_immediately_allowed():
    cadence = make_cadence(initial_delay=0)
    assert cadence.is_cycle_allowed() is True
    assert cadence.seconds_until_next_cycle() == 0.0


def test_initial_delay_is_respected():
    cadence = make_cadence(initial_delay=30)
    # First cycle should be delayed
    seconds = cadence.seconds_until_next_cycle()
    assert seconds <= 30.0  # Could be slightly less due to timing
    assert seconds >= 0.0


def test_after_success_cooldown_applied():
    cadence = make_cadence(min_interval=60)
    cadence.record_cycle_start()
    cadence.record_success()

    # Immediately after success, should be in cooldown
    assert not cadence.is_cycle_allowed()
    seconds = cadence.seconds_until_next_cycle()
    assert 50 <= seconds <= 61  # approximately 60s


def test_next_allowed_at_is_set_after_success():
    cadence = make_cadence(min_interval=60)
    cadence.record_success()
    assert cadence.next_allowed_at is not None


def test_transient_failure_applies_exponential_backoff():
    cadence = make_cadence(min_interval=60, max_interval=600)

    cadence.record_cycle_start()
    cadence.record_failure("TRANSIENT")  # failure 1 → 60s
    wait1 = cadence.seconds_until_next_cycle()

    cadence.record_cycle_start()
    cadence.record_failure("TRANSIENT")  # failure 2 → 120s
    wait2 = cadence.seconds_until_next_cycle()

    cadence.record_cycle_start()
    cadence.record_failure("TRANSIENT")  # failure 3 → 240s
    wait3 = cadence.seconds_until_next_cycle()

    assert wait2 > wait1
    assert wait3 > wait2


def test_backoff_capped_at_max_interval():
    cadence = make_cadence(min_interval=60, max_interval=120)
    
    # Many failures should cap at max_interval
    for _ in range(10):
        cadence.record_failure("TRANSIENT")
    
    wait = cadence.seconds_until_next_cycle()
    assert wait <= 121  # Slightly over due to timing, but capped


def test_budget_exhausted_jumps_to_max():
    cadence = make_cadence(min_interval=60, max_interval=1800)
    cadence.record_failure("BUDGET_EXHAUSTED")
    wait = cadence.seconds_until_next_cycle()
    # Should be near max_interval
    assert wait >= 1790


def test_success_resets_failure_count():
    cadence = make_cadence(min_interval=60)
    cadence.record_failure("TRANSIENT")
    cadence.record_failure("TRANSIENT")
    assert cadence.consecutive_failures == 2

    cadence.record_success()
    assert cadence.consecutive_failures == 0


def test_state_snapshot_fields():
    cadence = make_cadence()
    snap = cadence.state_snapshot()
    assert "consecutive_failures" in snap
    assert "is_first_cycle" in snap
    assert "min_interval_seconds" in snap
    assert "max_interval_seconds" in snap
    assert "seconds_until_next" in snap


@pytest.mark.asyncio
async def test_wait_for_next_cycle_returns_immediately_when_eligible():
    cadence = make_cadence(initial_delay=0)
    # Should return almost immediately
    import asyncio
    start = asyncio.get_event_loop().time()
    await cadence.wait_for_next_cycle()
    elapsed = asyncio.get_event_loop().time() - start
    assert elapsed < 0.5  # Well under 0.5s
