"""
Tests for LLMBudgetManager.
All tests are synchronous via pytest-asyncio.
No real API calls.
"""
import pytest
import asyncio
from app.runtime.budget import LLMBudgetManager
from unittest.mock import patch


@pytest.fixture
def budget():
    return LLMBudgetManager()


@pytest.mark.asyncio
async def test_initial_budget_is_full(budget):
    remaining = budget.remaining_budget()
    assert remaining["cycle_calls_used"] == 0
    assert remaining["cycle_calls_remaining"] > 0


@pytest.mark.asyncio
async def test_can_spend_within_limit(budget):
    assert await budget.can_spend(op="general", count=1) is True


@pytest.mark.asyncio
async def test_can_spend_exceeds_cycle_limit(budget):
    from app.config import settings
    # Exhaust the cycle budget
    token = await budget.reserve(op="test", count=settings.max_llm_calls_per_cycle)
    assert token is not None
    # Now should have no capacity
    assert await budget.can_spend(count=1) is False


@pytest.mark.asyncio
async def test_reserve_returns_token(budget):
    token = await budget.reserve(op="research", count=3)
    assert token is not None
    assert len(token) > 0


@pytest.mark.asyncio
async def test_reserve_and_release_restores_capacity(budget):
    from app.config import settings
    limit = settings.max_llm_calls_per_cycle
    token = await budget.reserve(op="research", count=limit)
    assert token is not None
    assert await budget.can_spend(count=1) is False

    # Release all as unused
    await budget.release(token, used=0)
    assert await budget.can_spend(count=1) is True


@pytest.mark.asyncio
async def test_reserve_and_release_commits_used_calls(budget):
    token = await budget.reserve(op="evidence_extraction", count=5)
    await budget.release(token, used=3)
    remaining = budget.remaining_budget()
    assert remaining["cycle_calls_used"] == 3


@pytest.mark.asyncio
async def test_release_unknown_token_is_safe(budget):
    # Should not raise
    await budget.release("nonexistent_token", used=1)


@pytest.mark.asyncio
async def test_record_failure_counts_toward_budget(budget):
    await budget.record_failure(reason="network timeout")
    stats = budget.cycle_stats_snapshot()
    assert stats["failed_calls"] == 1
    assert stats["llm_calls"] == 1


@pytest.mark.asyncio
async def test_record_429_increments_rate_limit_count(budget):
    await budget.record_failure(reason="429 rate_limit exceeded")
    stats = budget.cycle_stats_snapshot()
    assert stats["rate_limit_429"] == 1


@pytest.mark.asyncio
async def test_reset_cycle_clears_stats(budget):
    token = await budget.reserve(op="research", count=3)
    await budget.release(token, used=3)
    
    await budget.reset_cycle()
    
    remaining = budget.remaining_budget()
    assert remaining["cycle_calls_used"] == 0
    assert remaining["cycle_calls_reserved"] == 0


@pytest.mark.asyncio
async def test_reserve_returns_none_when_budget_exhausted(budget):
    from app.config import settings
    limit = settings.max_llm_calls_per_cycle
    token1 = await budget.reserve(op="test", count=limit)
    assert token1 is not None
    token2 = await budget.reserve(op="test", count=1)
    assert token2 is None


@pytest.mark.asyncio
async def test_concurrent_reservations_are_safe(budget):
    """Multiple concurrent reservations should not exceed limit."""
    from app.config import settings
    limit = settings.max_llm_calls_per_cycle

    # Try to reserve 2 at once, each asking for limit/2 + 1
    half = limit // 2 + 1

    results = await asyncio.gather(
        budget.reserve(op="a", count=half),
        budget.reserve(op="b", count=half),
        return_exceptions=True
    )
    tokens = [r for r in results if isinstance(r, str) and r is not None]
    nones = [r for r in results if r is None]

    # At most one should succeed (they exceed limit together)
    assert len(tokens) <= 1 or len(nones) >= 1


@pytest.mark.asyncio
async def test_remaining_budget_snapshot_is_correct(budget):
    from app.config import settings
    token = await budget.reserve(op="editorial", count=2)
    await budget.release(token, used=2)

    remaining = budget.remaining_budget()
    assert remaining["cycle_calls_used"] == 2
    assert remaining["cycle_calls_remaining"] == settings.max_llm_calls_per_cycle - 2
    assert remaining["total_llm_calls"] == 2
