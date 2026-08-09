"""
Resilience tests — verify runtime survives provider failures, quota exhaustion,
empty results, partial evidence, timeouts, and duplicate sources.

All tests use fake providers. No real API calls.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.runtime.budget import LLMBudgetManager
from app.runtime.cadence import CadenceController
from app.llm.provider import ProviderQuotaExhausted


# ─────────────────────────────────────────────────────────────
#  Provider Failure Tests
# ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_budget_exhausted_does_not_create_immediate_retry():
    """After budget exhaustion, cadence applies max backoff not zero."""
    cadence = CadenceController(min_interval=60, max_interval=1800)
    cadence.record_failure("BUDGET_EXHAUSTED")
    wait = cadence.seconds_until_next_cycle()
    assert wait >= 1700, f"Expected long wait after budget exhaustion, got {wait}s"


@pytest.mark.asyncio
async def test_transient_failure_applies_bounded_backoff():
    """Transient failures get exponential backoff, capped at max."""
    cadence = CadenceController(min_interval=60, max_interval=300)
    cadence.record_failure("TRANSIENT")
    wait1 = cadence.seconds_until_next_cycle()

    cadence.record_failure("TRANSIENT")
    wait2 = cadence.seconds_until_next_cycle()

    assert wait2 > wait1, "Second failure should have longer backoff"
    assert wait2 <= 301, "Should not exceed max interval"


@pytest.mark.asyncio
async def test_success_resets_backoff_after_multiple_failures():
    """After multiple failures, success resets to min_interval."""
    cadence = CadenceController(min_interval=60, max_interval=1800)
    cadence.record_failure("TRANSIENT")
    cadence.record_failure("TRANSIENT")
    cadence.record_failure("TRANSIENT")

    assert cadence.consecutive_failures == 3

    cadence.record_success()
    assert cadence.consecutive_failures == 0
    wait = cadence.seconds_until_next_cycle()
    assert wait <= 61, "Should be back to min interval after success"


@pytest.mark.asyncio
async def test_429_recorded_as_failure_in_budget():
    """429 responses are recorded and count against budget."""
    budget = LLMBudgetManager()
    await budget.record_failure(reason="HTTP 429 rate_limit_exceeded")
    
    stats = budget.cycle_stats_snapshot()
    assert stats["rate_limit_429"] >= 1
    assert stats["failed_calls"] >= 1
    # Failure still consumes budget to prevent retry storms
    assert stats["llm_calls"] >= 1


@pytest.mark.asyncio
async def test_budget_prevents_retry_storm():
    """After quota exhaustion fills budget, further reservations are blocked."""
    budget = LLMBudgetManager()
    from app.config import settings
    limit = settings.max_llm_calls_per_cycle
    
    # Simulate all budget consumed by failures
    for _ in range(limit):
        await budget.record_failure(reason="429 rate_limit")
    
    # No more budget should remain
    can = await budget.can_spend(count=1)
    assert can is False, "Budget should be exhausted after many failures"


@pytest.mark.asyncio
async def test_empty_search_results_dont_crash_budget():
    """Empty search results return PARTIAL, budget is released correctly."""
    budget = LLMBudgetManager()
    
    # Reserve research budget
    token = await budget.reserve(op="research", count=5)
    assert token is not None
    
    # Simulate: 0 sources found, 0 evidence calls used
    await budget.release(token, used=1)  # Only query gen call
    
    stats = budget.cycle_stats_snapshot()
    assert stats["llm_calls"] == 1
    assert stats["research_calls"] == 1


@pytest.mark.asyncio
async def test_partial_evidence_is_accepted():
    """Research run with PARTIAL status is still usable for beliefs."""
    from app.research.yield_tracker import ResearchYieldTracker
    
    db = AsyncMock()
    question = MagicMock()
    question.id = "q1"
    question.research_attempts = None
    question.successful_runs = None
    question.useful_evidence_count = None
    question.consecutive_low_yield_runs = None
    question.stagnant_until = None
    question.last_meaningful_change_at = None
    question.yield_score = None
    
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=question)))
    db.commit = AsyncMock()
    
    run = MagicMock()
    run.status = "PARTIAL"
    run.sources_discovered = ["url1", "url2", "url3"]
    run.sources_processed = ["url1"]  # Only 1 of 3 succeeded
    run.yield_score = None
    run.source_diversity_score = None
    run.contradiction_count = None
    run.belief_change_delta = None
    
    tracker = ResearchYieldTracker(db)
    yield_score = await tracker.record_run_yield(
        question_id="q1",
        run=run,
        evidence_ids=["e1", "e2"],  # Got some evidence
        contradiction_count=0,
        belief_change_delta=0.1,
        source_domains=["example.com"],
    )
    
    assert 0.0 <= yield_score <= 1.0
    db.commit.assert_called()


@pytest.mark.asyncio
async def test_stagnation_detection_sets_stagnant_until():
    """After N consecutive low-yield runs, question is marked stagnant."""
    from app.research.yield_tracker import ResearchYieldTracker
    from app.config import settings
    
    db = AsyncMock()
    question = MagicMock()
    question.id = "q-stagnant"
    question.research_attempts = 2
    question.successful_runs = 2
    question.useful_evidence_count = 0
    question.consecutive_low_yield_runs = settings.research_stagnation_threshold - 1
    question.stagnant_until = None
    question.last_meaningful_change_at = None
    question.yield_score = 0.1
    
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=question)))
    db.commit = AsyncMock()
    
    run = MagicMock()
    run.status = "COMPLETED"
    run.sources_discovered = ["url1"]
    run.sources_processed = ["url1"]
    run.yield_score = None
    run.source_diversity_score = None
    run.contradiction_count = None
    run.belief_change_delta = None
    
    tracker = ResearchYieldTracker(db)
    # This run also has low yield (0 evidence)
    await tracker.record_run_yield(
        question_id="q-stagnant",
        run=run,
        evidence_ids=[],       # Zero evidence = low yield
        contradiction_count=0,
        belief_change_delta=0.0,
        source_domains=["same.com"],
    )
    
    # stagnant_until should now be set
    assert question.stagnant_until is not None


@pytest.mark.asyncio
async def test_good_yield_resets_stagnation():
    """A high-yield run resets the consecutive_low_yield_runs counter."""
    from app.research.yield_tracker import ResearchYieldTracker
    
    db = AsyncMock()
    question = MagicMock()
    question.id = "q-good"
    question.research_attempts = 5
    question.successful_runs = 4
    question.useful_evidence_count = 10
    question.consecutive_low_yield_runs = 2
    question.stagnant_until = None
    question.last_meaningful_change_at = None
    question.yield_score = 0.3
    
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=question)))
    db.commit = AsyncMock()
    
    run = MagicMock()
    run.status = "COMPLETED"
    run.sources_discovered = ["url1", "url2", "url3"]
    run.sources_processed = ["url1", "url2", "url3"]
    run.yield_score = None
    run.source_diversity_score = None
    run.contradiction_count = None
    run.belief_change_delta = None
    
    tracker = ResearchYieldTracker(db)
    await tracker.record_run_yield(
        question_id="q-good",
        run=run,
        evidence_ids=["e1", "e2", "e3", "e4", "e5"],  # Good evidence
        contradiction_count=2,
        belief_change_delta=0.25,
        source_domains=["news.com", "research.edu", "gov.org"],
    )
    
    # Counter should be reset
    assert question.consecutive_low_yield_runs == 0
    assert question.stagnant_until is None


@pytest.mark.asyncio
async def test_duplicate_sources_dont_inflate_diversity():
    """Source diversity score is low for duplicate domains."""
    from app.research.yield_tracker import ResearchYieldTracker
    
    db = AsyncMock()
    tracker = ResearchYieldTracker(db)
    
    # All same domain = low diversity
    diversity_low = tracker._source_diversity(["news.com", "news.com", "news.com"])
    # Different domains = high diversity
    diversity_high = tracker._source_diversity(["news.com", "research.edu", "gov.org"])
    
    assert diversity_high > diversity_low
    assert diversity_low < 0.5
