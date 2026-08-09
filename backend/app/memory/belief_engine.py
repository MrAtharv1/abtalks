import uuid
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.db.models import Belief, BeliefEvidence, BeliefRevision, Evidence, ResearchQuestion
from app.llm.base import LLMProvider
from app.schemas.belief import GeneratedBeliefSynthesis, BeliefRevisionAnalysis

logger = logging.getLogger("thread")

SYNTHESIS_PROMPT = """
You are synthesizing the current state of knowledge for an autonomous research agent.

Research question:
{question}

Available evidence:
{evidence}

Your task is to identify concise, evidence-grounded beliefs.
Rules:
1. Every belief must be supported by the supplied evidence.
2. Do not introduce external facts.
3. Do not invent evidence.
4. Do not treat absence of evidence as evidence of absence.
5. Preserve meaningful uncertainty.
6. Preserve contradictions.
7. Keep beliefs specific and state appropriate scope.
8. Confidence must reflect the evidence quality and consistency (0.0 to 1.0).
9. Use EXACT evidence IDs provided in the Available evidence. Never invent an ID.
10. Return only structured output.
"""

REVISION_PROMPT = """
You are analyzing new evidence against an existing belief to determine if the belief should be revised.

Existing Belief:
{statement} (Scope: {scope})

New Evidence:
{evidence}

Determine the semantic relationship of the new evidence to the belief.
Valid relationships: SUPPORTS, CONTRADICTS, QUALIFIES, UNRELATED.
Provide a brief reason.
"""

def calculate_confidence_update(current: float, weight: float, relationship: str) -> float:
    """
    Deterministic bounded confidence update.
    """
    if relationship == "SUPPORTS":
        new_conf = current + (weight * 0.2)
    elif relationship == "CONTRADICTS":
        new_conf = current - (weight * 0.3)
    else:
        new_conf = current # QUALIFIES or UNRELATED don't strictly shift confidence up/down without human interpretation.
    
    return max(0.01, min(0.99, new_conf))

def determine_status(confidence: float, has_contradiction: bool) -> str:
    if has_contradiction and confidence < 0.6:
        return "DISPUTED"
    if confidence < 0.4:
        return "WEAKENED"
    if confidence < 0.1:
        return "ABANDONED"
    return "ACTIVE"

class BeliefService:
    def __init__(self, db: AsyncSession, llm_provider: LLMProvider):
        self.db = db
        self.llm = llm_provider

    def _format_evidence(self, ev_list: list[Evidence]) -> str:
        return "\n".join([f"ID: {e.id} | Quality: {e.source_quality_score} | Claim: {e.claim} | Text: {e.evidence_text}" for e in ev_list])

    async def synthesize_for_question(self, question_id: str):
        logger.info(f"[MEMORY] belief_synthesis_started for {question_id}")
        
        # Load question and all its evidence
        result = await self.db.execute(
            select(ResearchQuestion).options(selectinload(ResearchQuestion.evidence)).where(ResearchQuestion.id == question_id)
        )
        question = result.scalar_one_or_none()
        if not question or not question.evidence:
            logger.info("No question or evidence found.")
            return []
            
        evidence_str = self._format_evidence(question.evidence)
        prompt = SYNTHESIS_PROMPT.format(question=question.question, evidence=evidence_str)
        
        synthesis = await self.llm.generate_structured(prompt=prompt, schema=GeneratedBeliefSynthesis)
        logger.info(f"[MEMORY] beliefs_generated: {len(synthesis.beliefs)}")
        
        valid_ev_ids = {e.id for e in question.evidence}
        ev_map = {e.id: e for e in question.evidence}
        
        created_beliefs = []
        for b in synthesis.beliefs:
            belief_id = str(uuid.uuid4())
            # Clean hallucinated IDs
            supports = [eid for eid in b.supporting_evidence_ids if eid in valid_ev_ids]
            contradicts = [eid for eid in b.contradicting_evidence_ids if eid in valid_ev_ids]
            qualifies = [eid for eid in b.qualifying_evidence_ids if eid in valid_ev_ids]
            
            if not supports and not contradicts and not qualifies:
                logger.warning("Rejecting belief: no valid grounded evidence IDs.")
                continue
                
            has_contradiction = len(contradicts) > 0
            status = determine_status(b.initial_confidence, has_contradiction)
            
            belief_model = Belief(
                id=belief_id,
                agent_id=question.thread.agent_id, # Assume thread loaded or use alternative query
                thread_id=question.thread_id,
                statement=b.statement,
                confidence=b.initial_confidence,
                importance=b.importance,
                status=status,
                scope=b.scope
            )
            self.db.add(belief_model)
            
            # Create revision 0 (INITIAL)
            rev = BeliefRevision(
                id=str(uuid.uuid4()),
                belief_id=belief_id,
                previous_confidence=0.0,
                new_confidence=b.initial_confidence,
                change_type="INITIAL",
                reason="Initial synthesis from available evidence."
            )
            self.db.add(rev)
            
            # Create Evidence Links
            for rel, eids in [("SUPPORTS", supports), ("CONTRADICTS", contradicts), ("QUALIFIES", qualifies)]:
                for eid in eids:
                    ev = ev_map[eid]
                    weight = ev.source_quality_score * ev.confidence * ev.relevance_score
                    link = BeliefEvidence(
                        id=str(uuid.uuid4()),
                        belief_id=belief_id,
                        evidence_id=eid,
                        relationship_type=rel,
                        weight=weight
                    )
                    self.db.add(link)
            
            created_beliefs.append(belief_model)
            logger.info(f"[MEMORY] belief_created: {belief_id}")
            
        await self.db.commit()
        return created_beliefs

    async def revise_beliefs(self, belief_id: str, new_evidence_ids: list[str]):
        logger.info(f"[MEMORY] belief_revision_started for {belief_id}")
        
        result = await self.db.execute(
            select(Belief).options(selectinload(Belief.evidence_links)).where(Belief.id == belief_id)
        )
        belief = result.scalar_one_or_none()
        if not belief:
            return
            
        ev_result = await self.db.execute(
            select(Evidence).where(Evidence.id.in_(new_evidence_ids))
        )
        new_evidence_list = ev_result.scalars().all()
        if not new_evidence_list:
            return
            
        evidence_str = self._format_evidence(new_evidence_list)
        prompt = REVISION_PROMPT.format(statement=belief.statement, scope=belief.scope, evidence=evidence_str)
        
        analysis = await self.llm.generate_structured(prompt=prompt, schema=BeliefRevisionAnalysis)
        
        # We must process atomically
        current_conf = belief.confidence
        has_contradiction = any(link.relationship_type == "CONTRADICTS" for link in belief.evidence_links)
        
        for ans in analysis.analyses:
            if ans.relationship == "UNRELATED":
                continue
                
            ev = next((e for e in new_evidence_list if e.id == ans.evidence_id), None)
            if not ev:
                continue
                
            weight = ev.source_quality_score * ev.confidence * ev.relevance_score
            new_conf = calculate_confidence_update(current_conf, weight, ans.relationship)
            
            if ans.relationship == "CONTRADICTS":
                has_contradiction = True
                
            change_type = "WEAKENED" if new_conf < current_conf else ("STRENGTHENED" if new_conf > current_conf else "QUALIFIED")
            
            link = BeliefEvidence(
                id=str(uuid.uuid4()),
                belief_id=belief.id,
                evidence_id=ev.id,
                relationship_type=ans.relationship,
                weight=weight
            )
            self.db.add(link)
            
            rev = BeliefRevision(
                id=str(uuid.uuid4()),
                belief_id=belief.id,
                previous_confidence=current_conf,
                new_confidence=new_conf,
                change_type=change_type,
                reason=ans.reason,
                trigger_evidence_id=ev.id
            )
            self.db.add(rev)
            
            logger.info(f"[MEMORY] belief_{change_type.lower()}: {current_conf:.2f} -> {new_conf:.2f}")
            current_conf = new_conf

        belief.confidence = current_conf
        belief.status = determine_status(current_conf, has_contradiction)
        belief.last_revised_at = datetime.utcnow()
        
        await self.db.commit()
        logger.info(f"[MEMORY] belief_revision_completed")
