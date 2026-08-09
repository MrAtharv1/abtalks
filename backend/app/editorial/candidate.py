import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.db.models import Agent, Belief, BeliefRevision, EditorialCandidate, PersonaProfile
from app.llm.base import LLMProvider
from app.schemas.editorial import GeneratedEditorialCandidate
import logging

logger = logging.getLogger("thread")

class CandidateService:
    def __init__(self, db: AsyncSession, llm: LLMProvider):
        self.db = db
        self.llm = llm

    async def generate_candidates(self, agent_id: str) -> list[EditorialCandidate]:
        """
        Looks for recent BeliefRevisions that have NOT been converted into an EditorialCandidate yet.
        """
        logger.info(f"[EDITORIAL] Generating candidates for agent {agent_id}")
        
        # 1. Fetch persona
        agent_res = await self.db.execute(
            select(Agent).options(selectinload(Agent.persona)).where(Agent.id == agent_id)
        )
        agent = agent_res.scalar_one_or_none()
        if not agent:
            return []
        
        # 2. Fetch unpublished revisions (revisions without a PENDING or SELECTED candidate)
        # For simplicity, we just fetch revisions that don't have ANY candidate pointing to them.
        from app.db.models import BeliefEvidence
        revisions_res = await self.db.execute(
            select(BeliefRevision)
            .options(
                selectinload(BeliefRevision.belief).selectinload(Belief.evidence_links).selectinload(BeliefEvidence.evidence),
                selectinload(BeliefRevision.trigger_evidence)
            )
            .join(BeliefRevision.belief)
            .where(Belief.agent_id == agent_id)
            .outerjoin(EditorialCandidate, EditorialCandidate.revision_id == BeliefRevision.id)
            .where(EditorialCandidate.id == None)
            .order_by(BeliefRevision.created_at.desc())
            .limit(5)
        )
        revisions = revisions_res.scalars().all()
        
        # --- Quota Optimization: Only process the single most significant revision ---
        if revisions:
            revisions.sort(key=lambda r: abs(r.new_confidence - r.previous_confidence), reverse=True)
            revisions = revisions[:1]
        
        candidates = []
        for rev in revisions:
            belief = rev.belief
            evidence = rev.trigger_evidence
            
            prompt = (
                f"Evaluate this belief revision for its potential as an editorial story.\n"
                f"Persona: {agent.persona.name} ({agent.persona.domain})\n"
                f"Belief: {belief.statement}\n"
                f"Previous Confidence: {rev.previous_confidence}, New Confidence: {rev.new_confidence}\n"
                f"Trigger Evidence: {evidence.evidence_text if evidence else 'N/A'}\n"
                f"Reason for change: {rev.reason}\n"
            )
            
            try:
                gen_cand = await self.llm.generate_structured(prompt, GeneratedEditorialCandidate)
                
                # We calculate raw novelty/evidence strength deterministically or via LLM in scorer.
                # Here we just initialize the model.
                candidate = EditorialCandidate(
                    id=str(uuid.uuid4()),
                    agent_id=agent_id,
                    belief_id=belief.id,
                    revision_id=rev.id,
                    question_id=belief.evidence_links[0].evidence.question_id if belief.evidence_links else None,
                    headline=gen_cand.headline,
                    summary=gen_cand.summary,
                    editorial_significance=gen_cand.editorial_significance,
                    novelty_score=0.0,
                    relevance_score=gen_cand.relevance_score,
                    evidence_strength=0.0,
                    persona_fit_score=0.0,
                    timeliness_score=0.0,
                    continuity_score=0.0,
                    competition_score=0.0,
                    status="PENDING"
                )
                self.db.add(candidate)
                candidates.append(candidate)
            except Exception as e:
                logger.error(f"[EDITORIAL] Failed to generate candidate for revision {rev.id}: {e}")
                
        if candidates:
            await self.db.commit()
            
        return candidates
