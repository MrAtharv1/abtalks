"""
LLMBudgetManager — centralized, thread-safe budget tracking for the THREAD runtime.

Tracks LLM calls, research calls, evidence extraction calls, editorial calls,
failed calls, 429 responses, and timeouts. Supports reservation-based budgeting
to prevent mid-operation quota exhaustion.

Usage:
    budget = LLMBudgetManager()
    if budget.can_spend(op="evidence_extraction", count=3):
        token = await budget.reserve(op="evidence_extraction", count=3)
        try:
            # do work
            budget.release(token, used=2)  # release unused capacity
        finally:
            pass  # used capacity already recorded on reserve
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict

from app.config import settings

logger = logging.getLogger("thread")


@dataclass
class BudgetReservation:
    """Tracks a reserved-but-not-yet-used budget allocation."""
    token: str
    operation: str
    reserved: int
    used: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CycleStats:
    """Stats for the current cycle."""
    llm_calls: int = 0
    research_calls: int = 0
    evidence_calls: int = 0
    editorial_calls: int = 0
    failed_calls: int = 0
    rate_limit_429: int = 0
    timeouts: int = 0
    tokens_used: int = 0  # if provider exposes token count


@dataclass
class HourlyStats:
    """Rolling 60-minute window stats."""
    llm_calls: int = 0
    window_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class LLMBudgetManager:
    """
    Centralized LLM budget manager.

    Operations:
        can_spend(op, count)    → bool  — check without reserving
        reserve(op, count)      → str   — reserve budget, returns reservation token
        release(token, used)            — release unused reservation capacity
        record_failure(reason)          — track failed calls / 429s / timeouts
        record_tokens(n)                — record actual token usage if available
        remaining_budget()       → dict  — current remaining capacity
        reset_cycle()                   — call at the start of each new cycle

    Thread safety: all mutations go through asyncio.Lock().
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self._cycle_stats = CycleStats()
        self._hourly_stats = HourlyStats()
        self._reservations: Dict[str, BudgetReservation] = {}
        self._reserved_calls: int = 0  # total calls currently reserved (not yet used)
        self._cycle_count: int = 0
        self._total_llm_calls: int = 0
        self._total_429s: int = 0

    async def can_spend(self, op: str = "general", count: int = 1) -> bool:
        """
        Returns True if there is sufficient budget for `count` LLM calls.
        Does NOT reserve any capacity.
        """
        async with self._lock:
            return self._has_capacity(count)

    def _has_capacity(self, count: int) -> bool:
        """Internal capacity check (must be called within lock)."""
        # Per-cycle limit
        committed = self._cycle_stats.llm_calls + self._reserved_calls
        if committed + count > settings.max_llm_calls_per_cycle:
            logger.debug(
                f"[BUDGET] Per-cycle limit reached: committed={committed}, "
                f"requested={count}, limit={settings.max_llm_calls_per_cycle}"
            )
            return False

        # Per-hour limit (rolling window check)
        self._refresh_hourly_window()
        if self._hourly_stats.llm_calls + count > settings.max_llm_calls_per_hour:
            logger.debug(
                f"[BUDGET] Per-hour limit reached: used={self._hourly_stats.llm_calls}, "
                f"requested={count}, limit={settings.max_llm_calls_per_hour}"
            )
            return False

        return True

    def _refresh_hourly_window(self):
        """Reset hourly stats if window has expired (called within lock)."""
        now = datetime.now(timezone.utc)
        elapsed = (now - self._hourly_stats.window_start).total_seconds()
        if elapsed >= 3600:
            self._hourly_stats = HourlyStats()

    async def reserve(self, op: str, count: int = 1) -> str | None:
        """
        Reserve `count` calls for operation `op`.
        Returns a reservation token, or None if insufficient budget.
        The reservation is committed immediately — call release() with actual used count.
        """
        import uuid
        async with self._lock:
            if not self._has_capacity(count):
                logger.info(f"[BUDGET] Cannot reserve {count} calls for '{op}': budget exhausted")
                return None

            token = str(uuid.uuid4())[:8]
            reservation = BudgetReservation(token=token, operation=op, reserved=count)
            self._reservations[token] = reservation
            self._reserved_calls += count
            logger.debug(f"[BUDGET] Reserved {count} calls for '{op}' (token={token})")
            return token

    async def release(self, token: str, used: int):
        """
        Commit `used` calls to the cycle stats and release unused reservation capacity.
        Must be called after every reserve(), regardless of success/failure.
        """
        async with self._lock:
            reservation = self._reservations.pop(token, None)
            if not reservation:
                logger.warning(f"[BUDGET] Unknown reservation token {token}")
                return

            unused = reservation.reserved - used
            self._reserved_calls = max(0, self._reserved_calls - reservation.reserved)

            # Commit actual used calls
            self._cycle_stats.llm_calls += used
            self._hourly_stats.llm_calls += used
            self._total_llm_calls += used

            op = reservation.operation
            if op == "evidence_extraction":
                self._cycle_stats.evidence_calls += used
            elif op == "research":
                self._cycle_stats.research_calls += used
            elif op in ("editorial", "authoring", "candidate"):
                self._cycle_stats.editorial_calls += used

            logger.debug(
                f"[BUDGET] Released token={token} op={op} "
                f"reserved={reservation.reserved} used={used} unused={unused}"
            )

    async def record_failure(self, reason: str = "unknown"):
        """Record a failed LLM call (counts against budget to prevent retry storms)."""
        async with self._lock:
            self._cycle_stats.failed_calls += 1
            if "429" in reason or "rate_limit" in reason or "quota" in reason.lower():
                self._cycle_stats.rate_limit_429 += 1
                self._total_429s += 1
            elif "timeout" in reason.lower():
                self._cycle_stats.timeouts += 1
            # Failed calls still consume budget to prevent storms
            self._cycle_stats.llm_calls += 1
            self._hourly_stats.llm_calls += 1
            self._total_llm_calls += 1

    async def record_tokens(self, n: int):
        """Record actual token usage if exposed by the provider."""
        async with self._lock:
            self._cycle_stats.tokens_used += n

    def remaining_budget(self) -> dict:
        """Return current budget remaining (snapshot, not locked)."""
        committed = self._cycle_stats.llm_calls + self._reserved_calls
        return {
            "cycle_calls_used": self._cycle_stats.llm_calls,
            "cycle_calls_reserved": self._reserved_calls,
            "cycle_calls_remaining": max(0, settings.max_llm_calls_per_cycle - committed),
            "cycle_calls_limit": settings.max_llm_calls_per_cycle,
            "hourly_calls_used": self._hourly_stats.llm_calls,
            "hourly_calls_remaining": max(0, settings.max_llm_calls_per_hour - self._hourly_stats.llm_calls),
            "hourly_calls_limit": settings.max_llm_calls_per_hour,
            "total_llm_calls": self._total_llm_calls,
            "total_429s": self._total_429s,
            "failed_calls": self._cycle_stats.failed_calls,
        }

    async def reset_cycle(self):
        """Reset per-cycle counters. Call at the start of each new cycle."""
        async with self._lock:
            self._cycle_stats = CycleStats()
            self._reserved_calls = 0
            # Abandon dangling reservations (from previous failed cycle)
            self._reservations.clear()
            self._cycle_count += 1
            self._refresh_hourly_window()
            logger.debug(f"[BUDGET] Cycle reset. Cycle #{self._cycle_count}")

    def cycle_stats_snapshot(self) -> dict:
        """Snapshot of current cycle stats (no lock needed for read)."""
        return {
            "llm_calls": self._cycle_stats.llm_calls,
            "research_calls": self._cycle_stats.research_calls,
            "evidence_calls": self._cycle_stats.evidence_calls,
            "editorial_calls": self._cycle_stats.editorial_calls,
            "failed_calls": self._cycle_stats.failed_calls,
            "rate_limit_429": self._cycle_stats.rate_limit_429,
            "timeouts": self._cycle_stats.timeouts,
            "tokens_used": self._cycle_stats.tokens_used,
            "cycle_count": self._cycle_count,
        }
