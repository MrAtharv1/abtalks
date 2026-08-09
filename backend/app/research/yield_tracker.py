"""
ResearchYieldTracker — measures and persists research quality per question.

Yield score formula:
    yield = (meaningful_evidence × 0.4)
           + (contradiction_bonus × 0.3)
           + (belief_change_delta × 0.2)
           + (source_diversity × 0.1)
           - (redundancy_penalty)

All factors normalized to 0..1.

Updates ResearchQuestion stats after each run:
    - research_attempts
    - successful_runs
    - useful_evidence_count
    - consecutive_low_yield_runs
    - last_meaningful_change_at
    - yield_score (rolling average)
    - stagnant_until (set if stagnation threshold crossed)
"""
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import settings
from app.db.models import ResearchQuestion, ResearchRun

logger = logging.getLogger("thread")


class ResearchYieldTracker:
    """
    Measures research run quality and updates question-level yield memory.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_run_yield(
        self,
        question_id: str,
        run: ResearchRun,
        evidence_ids: list[str],
        contradiction_count: int,
        belief_change_delta: float,
        source_domains: list[str],
    ) -> float:
        """
        Calculate and persist the yield score for a completed research run.
        Returns the computed yield score (0..1).
        """
        yield_score = self._compute_yield(
            evidence_ids=evidence_ids,
            run=run,
            contradiction_count=contradiction_count,
            belief_change_delta=belief_change_delta,
            source_domains=source_domains,
        )

        # Persist yield on the run record
        run.yield_score = yield_score
        run.contradiction_count = contradiction_count
        run.belief_change_delta = belief_change_delta
        run.source_diversity_score = self._source_diversity(source_domains)

        # Update question-level stats
        result = await self.db.execute(
            select(ResearchQuestion).where(ResearchQuestion.id == question_id)
        )
        question = result.scalar_one_or_none()
        if not question:
            return yield_score

        # Increment attempts
        attempts = (getattr(question, "research_attempts", None) or 0) + 1
        question.research_attempts = attempts

        is_useful = yield_score >= settings.research_yield_low_threshold
        useful_count = (getattr(question, "useful_evidence_count", None) or 0) + len(evidence_ids)
        question.useful_evidence_count = useful_count

        if run.status in ("COMPLETED", "PARTIAL"):
            question.successful_runs = (getattr(question, "successful_runs", None) or 0) + 1

        if is_useful:
            # Reset stagnation counter
            question.consecutive_low_yield_runs = 0
            question.last_meaningful_change_at = datetime.now(timezone.utc)
            question.stagnant_until = None
        else:
            consecutive = (getattr(question, "consecutive_low_yield_runs", None) or 0) + 1
            question.consecutive_low_yield_runs = consecutive

            if consecutive >= settings.research_stagnation_threshold:
                cooldown = settings.research_stagnation_cooldown_seconds
                question.stagnant_until = datetime.now(timezone.utc) + timedelta(seconds=cooldown)
                logger.info(
                    f"[YIELD] question_stagnant id={question_id[:8]} "
                    f"consecutive_low_yield={consecutive} "
                    f"stagnant_until={question.stagnant_until.isoformat()}"
                )

        # Rolling average yield score (exponential moving average, α=0.3)
        old_yield = getattr(question, "yield_score", None) or 0.0
        if attempts == 1:
            question.yield_score = yield_score
        else:
            question.yield_score = (0.7 * old_yield) + (0.3 * yield_score)

        await self.db.commit()

        logger.info(
            f"[YIELD] run_yield_recorded question={question_id[:8]} "
            f"yield={yield_score:.3f} evidence={len(evidence_ids)} "
            f"contradictions={contradiction_count} "
            f"belief_delta={belief_change_delta:.3f} "
            f"consecutive_low={question.consecutive_low_yield_runs}"
        )

        return yield_score

    def _compute_yield(
        self,
        evidence_ids: list[str],
        run: ResearchRun,
        contradiction_count: int,
        belief_change_delta: float,
        source_domains: list[str],
    ) -> float:
        """Compute normalized yield score (0..1)."""

        # 1. Meaningful evidence factor (saturates at 5+ items)
        evidence_factor = min(1.0, len(evidence_ids) / 5.0)

        # 2. Contradiction bonus (finding disagreement is valuable)
        contradiction_factor = min(1.0, contradiction_count / 3.0)

        # 3. Belief change delta (normalized to 0..1 range)
        belief_factor = min(1.0, abs(belief_change_delta))

        # 4. Source diversity (unique domains)
        diversity_factor = self._source_diversity(source_domains)

        # 5. Redundancy penalty (if we processed very few of what we discovered)
        discovered = len(run.sources_discovered or [])
        processed = len(run.sources_processed or [])
        if discovered > 0:
            redundancy_penalty = max(0.0, 1.0 - (processed / discovered)) * 0.2
        else:
            redundancy_penalty = 0.3  # No sources → low value

        raw_score = (
            evidence_factor * 0.4
            + contradiction_factor * 0.3
            + belief_factor * 0.2
            + diversity_factor * 0.1
            - redundancy_penalty
        )

        return max(0.0, min(1.0, raw_score))

    def _source_diversity(self, domains: list[str]) -> float:
        """Calculate domain diversity (unique domains / total, capped at 1)."""
        if not domains:
            return 0.0
        unique = len(set(domains))
        return min(1.0, unique / max(1, len(domains)))
