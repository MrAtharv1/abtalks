from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.db.models import Agent, BeliefRevision, EditorialCandidate, Post

class ScorerService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def score_candidates(self, candidates: list[EditorialCandidate]) -> None:
        """
        Calculates a deterministic editorial score.
        Score = 0.25 * belief_change 
              + 0.20 * persona_relevance 
              + 0.15 * evidence_strength 
              + 0.15 * novelty 
              + 0.10 * timeliness 
              + 0.10 * continuity 
              + 0.05 * uncertainty
        """
        for cand in candidates:
            # 1. Belief Change
            rev_res = await self.db.execute(select(BeliefRevision).where(BeliefRevision.id == cand.revision_id))
            rev = rev_res.scalar_one_or_none()
            
            belief_change = 0.0
            uncertainty = 0.0
            
            if rev:
                diff = abs(rev.new_confidence - rev.previous_confidence)
                belief_change = diff
                # Status transition logic
                if rev.change_type == "DISPUTED":
                    belief_change = min(1.0, belief_change + 0.3)
                    uncertainty = 0.8
                elif rev.change_type == "WEAKENED":
                    belief_change = min(1.0, belief_change + 0.1)
                    uncertainty = 0.6
                
                # If we are totally uncertain now
                if rev.new_confidence < 0.4:
                    uncertainty = max(uncertainty, 1.0 - rev.new_confidence)
            
            cand.novelty_score = 1.0
            cand.evidence_strength = 0.8
            cand.persona_fit_score = cand.relevance_score
            cand.timeliness_score = 1.0
            cand.continuity_score = 0.5
            
            # Repetition penalty (check previous posts for same belief)
            posts_res = await self.db.execute(
                select(Post)
                .where(Post.agent_id == cand.agent_id)
                .where(Post.belief_id == cand.belief_id)
            )
            previous_posts = posts_res.scalars().all()
            if len(previous_posts) > 0:
                cand.novelty_score = 0.2 # Heavily penalize repeating the same belief
                if belief_change > 0.2:
                    # But if it's a major change, novelty penalty is reduced
                    cand.novelty_score = 0.6
            
            # Weighted sum
            final_score = (
                0.25 * belief_change +
                0.20 * cand.persona_fit_score +
                0.15 * cand.evidence_strength +
                0.15 * cand.novelty_score +
                0.10 * cand.timeliness_score +
                0.10 * cand.continuity_score +
                0.05 * uncertainty
            )
            cand.competition_score = final_score
            
        await self.db.commit()
