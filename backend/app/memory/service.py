from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.db.models import Belief, BeliefRevision, BeliefEvidence, Evidence

class MemoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_agent_beliefs(self, agent_id: str):
        result = await self.db.execute(
            select(Belief)
            .options(
                selectinload(Belief.evidence_links).selectinload(BeliefEvidence.evidence),
                selectinload(Belief.revisions)
            )
            .where(Belief.agent_id == agent_id)
        )
        return result.scalars().all()

    async def get_belief_history(self, belief_id: str):
        result = await self.db.execute(
            select(BeliefRevision)
            .where(BeliefRevision.belief_id == belief_id)
            .order_by(BeliefRevision.created_at.asc())
        )
        return result.scalars().all()

    async def get_relevant_beliefs(self, question_id: str):
        result = await self.db.execute(
            select(Belief)
            .options(
                selectinload(Belief.evidence_links).selectinload(BeliefEvidence.evidence),
                selectinload(Belief.revisions)
            )
            .join(BeliefEvidence, Belief.id == BeliefEvidence.belief_id)
            .join(Evidence, BeliefEvidence.evidence_id == Evidence.id)
            .where(Evidence.question_id == question_id)
        )
        # Unique beliefs for the question based on linked evidence
        return list({b.id: b for b in result.scalars().all()}.values())
