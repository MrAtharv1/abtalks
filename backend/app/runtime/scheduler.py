"""
ResearchScheduler — selects the best research question for the next cycle.

Phase 7 enhancements:
    - Yield-weighted scoring (historical research yield)
    - Stagnation gate (skips stagnant questions)
    - Contradiction-first bonus
    - Expected Information Value (EIV) scoring
    - Integrates with ResearchOpportunityGate for per-question decisions
"""
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.db.models import ResearchQuestion, ResearchThread
from app.config import settings
from app.runtime.opportunity import ResearchOpportunityGate

import logging
logger = logging.getLogger("thread")


class ResearchScheduler:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.gate = ResearchOpportunityGate()

    async def select_next_question(self, agent_id: str) -> ResearchQuestion | None:
        """
        Select the highest-value research question for the next cycle.

        Scoring:
            EIV = importance × uncertainty × yield_multiplier × freshness × thread_priority

        Questions are filtered through the ResearchOpportunityGate first.
        Returns None if no eligible question exists.
        """
        result = await self.db.execute(
            select(ResearchQuestion)
            .join(ResearchThread)
            .where(ResearchThread.agent_id == agent_id)
            .where(ResearchThread.status == "ACTIVE")
            .options(selectinload(ResearchQuestion.thread))
        )
        questions = result.scalars().all()

        if not questions:
            return None

        now = datetime.now(timezone.utc)

        # Use the opportunity gate to rank eligible questions
        ranked = self.gate.rank_questions(questions, now)

        if not ranked:
            logger.info(
                f"[SCHEDULER] No eligible questions for agent {agent_id} "
                f"(all gated or stagnant)"
            )
            return None

        best_score, best_q = ranked[0]
        logger.info(
            f"[SCHEDULER] question_selected id={best_q.id[:8]} "
            f"score={best_score:.3f} q={best_q.question[:60]}"
        )
        return best_q

    async def select_contradiction_question(self, agent_id: str) -> ResearchQuestion | None:
        """
        Select a question specifically for contradiction-first research.
        Prioritizes questions with existing high-confidence beliefs (>0.7)
        where contradictory evidence would be most epistemically valuable.
        """
        result = await self.db.execute(
            select(ResearchQuestion)
            .join(ResearchThread)
            .where(ResearchThread.agent_id == agent_id)
            .where(ResearchThread.status == "ACTIVE")
            .where(ResearchQuestion.confidence > 0.7)
            .options(selectinload(ResearchQuestion.thread))
        )
        questions = result.scalars().all()

        if not questions:
            return None

        now = datetime.now(timezone.utc)

        # Among high-confidence questions, pick the most important one
        # (where finding a contradiction would be most valuable)
        best = max(questions, key=lambda q: q.importance * q.confidence, default=None)

        if best:
            logger.info(
                f"[SCHEDULER] contradiction_target id={best.id[:8]} "
                f"confidence={best.confidence:.2f} q={best.question[:60]}"
            )

        return best
