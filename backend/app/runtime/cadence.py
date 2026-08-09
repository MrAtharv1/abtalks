"""
CadenceController — manages runtime cycle timing with exponential backoff.

The controller decides when the next cycle is allowed to start.
It distinguishes transient failures (backoff with cap) from budget exhaustion
(long wait before retrying) and permanent failures (stop).

States influence the cadence but the actual runtime state machine lives in state.py.
"""
import asyncio
import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Literal

from app.config import settings

logger = logging.getLogger("thread")

FailureType = Literal["TRANSIENT", "BUDGET_EXHAUSTED", "PERMANENT"]


class CadenceController:
    """
    Controls cycle timing using adaptive backoff.

    Normal cadence:
        min_interval → between cycles on success
    
    Failure cadence (exponential):
        base_interval × 2^failures, capped at max_interval

    Budget exhaustion:
        jumps directly to max_interval (no point retrying sooner)
    
    All times in seconds.
    """

    def __init__(
        self,
        min_interval: int | None = None,
        max_interval: int | None = None,
        initial_delay: int | None = None,
    ):
        self._min_interval = min_interval if min_interval is not None else settings.effective_min_cycle_interval
        self._max_interval = max_interval if max_interval is not None else settings.runtime_max_cycle_interval_seconds
        self._initial_delay = initial_delay if initial_delay is not None else settings.runtime_initial_delay_seconds

        self._consecutive_failures: int = 0
        self._last_cycle_started_at: datetime | None = None
        self._last_cycle_completed_at: datetime | None = None
        self._next_allowed_at: datetime | None = None
        self._is_first_cycle: bool = True

    def record_cycle_start(self):
        """Call at the beginning of each cycle."""
        self._last_cycle_started_at = datetime.now(timezone.utc)

    def record_success(self):
        """Call after a successful cycle. Resets failure backoff."""
        self._consecutive_failures = 0
        self._last_cycle_completed_at = datetime.now(timezone.utc)
        self._next_allowed_at = datetime.now(timezone.utc) + timedelta(seconds=self._min_interval)
        self._is_first_cycle = False
        logger.debug(
            f"[CADENCE] Success recorded. Next cycle allowed at "
            f"{self._next_allowed_at.isoformat()}Z (in {self._min_interval}s)"
        )

    def record_failure(self, failure_type: FailureType = "TRANSIENT"):
        """Call after a failed cycle. Applies appropriate backoff."""
        self._consecutive_failures += 1
        self._last_cycle_completed_at = datetime.now(timezone.utc)
        self._is_first_cycle = False

        if failure_type == "BUDGET_EXHAUSTED":
            # Don't bother retrying quickly — the budget won't recover for a while
            wait = self._max_interval
            logger.warning(
                f"[CADENCE] Budget exhaustion detected. Backing off for {wait}s "
                f"(max interval)."
            )
        elif failure_type == "PERMANENT":
            # Permanent failure — use max interval as a soft stop
            wait = self._max_interval
            logger.error(
                f"[CADENCE] Permanent failure. Will retry at max interval ({wait}s)."
            )
        else:
            # TRANSIENT: exponential backoff capped at max_interval
            # wait = min_interval × 2^(failures-1), capped
            exponent = self._consecutive_failures - 1
            wait = min(self._min_interval * (2 ** exponent), self._max_interval)
            logger.warning(
                f"[CADENCE] Transient failure #{self._consecutive_failures}. "
                f"Backoff: {wait}s (cap={self._max_interval}s)"
            )

        self._next_allowed_at = datetime.now(timezone.utc) + timedelta(seconds=wait)

    def seconds_until_next_cycle(self) -> float:
        """Returns seconds until the next cycle is allowed. 0 if eligible now."""
        if self._is_first_cycle:
            return max(0.0, float(self._initial_delay))

        if self._next_allowed_at is None:
            return 0.0

        now = datetime.now(timezone.utc)
        delta = (self._next_allowed_at - now).total_seconds()
        return max(0.0, delta)

    def is_cycle_allowed(self) -> bool:
        """Returns True if a new cycle can start immediately."""
        return self.seconds_until_next_cycle() == 0.0

    async def wait_for_next_cycle(self, stop_event: asyncio.Event = None):
        """Async sleep until the next cycle is allowed or stop_event is set. Returns immediately if eligible."""
        wait = self.seconds_until_next_cycle()
        if wait > 0:
            logger.info(f"[CADENCE] Sleeping {wait:.1f}s until next cycle.")
            if stop_event:
                sleep_task = asyncio.create_task(asyncio.sleep(wait))
                stop_task = asyncio.create_task(stop_event.wait())
                done, pending = await asyncio.wait(
                    [sleep_task, stop_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                for t in pending:
                    t.cancel()
            else:
                await asyncio.sleep(wait)

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    @property
    def next_allowed_at(self) -> datetime | None:
        return self._next_allowed_at

    def state_snapshot(self) -> dict:
        return {
            "consecutive_failures": self._consecutive_failures,
            "is_first_cycle": self._is_first_cycle,
            "min_interval_seconds": self._min_interval,
            "max_interval_seconds": self._max_interval,
            "next_allowed_at": self._next_allowed_at.isoformat() if self._next_allowed_at else None,
            "seconds_until_next": self.seconds_until_next_cycle(),
        }
