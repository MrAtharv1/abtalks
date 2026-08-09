import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import EditorialCandidate, EditorialDecision

class SelectorService:
    def __init__(self, db: AsyncSession, threshold: float = 0.5):
        self.db = db
        self.threshold = threshold

    async def select_candidate(self, candidates: list[EditorialCandidate]) -> EditorialCandidate | None:
        if not candidates:
            return None
            
        # Sort by competition_score descending
        candidates.sort(key=lambda x: x.competition_score, reverse=True)
        
        top_candidate = candidates[0]
        selected = None
        
        if top_candidate.competition_score >= self.threshold:
            top_candidate.status = "SELECTED"
            selected = top_candidate
            
            decision = EditorialDecision(
                id=str(uuid.uuid4()),
                agent_id=top_candidate.agent_id,
                candidate_id=top_candidate.id,
                selected="SELECTED", # Maps to boolean logic in test
                score=top_candidate.competition_score,
                decision_type="SELECTED",
                reason="Highest scoring candidate above threshold"
            )
            self.db.add(decision)
        
        # Reject others
        for cand in candidates:
            if cand != selected:
                cand.status = "REJECTED"
                decision = EditorialDecision(
                    id=str(uuid.uuid4()),
                    agent_id=cand.agent_id,
                    candidate_id=cand.id,
                    selected="REJECTED",
                    score=cand.competition_score,
                    decision_type="REJECTED",
                    reason="Outscored by another candidate or below threshold"
                )
                self.db.add(decision)
                
        await self.db.commit()
        return selected
