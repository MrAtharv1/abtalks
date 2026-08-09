import uuid
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.db.models import Agent, EditorialCandidate, Post, Source, Belief
from app.llm.base import LLMProvider
from app.schemas.editorial import GeneratedPost
from app.editorial.quality_gate import PostQualityGate
import logging

logger = logging.getLogger("thread")


class AuthorService:
    def __init__(self, db: AsyncSession, llm: LLMProvider):
        self.db = db
        self.llm = llm

    async def generate_post(self, candidate: EditorialCandidate) -> Post | None:
        """
        Legacy entry point — calls generate_post_with_gate with default gate.
        """
        return await self.generate_post_with_gate(
            candidate=candidate,
            recent_post_texts=[],
            known_evidence_ids=set(),
            quality_gate=PostQualityGate(),
        )

    async def generate_post_with_gate(
        self,
        candidate: EditorialCandidate,
        recent_post_texts: list[str],
        known_evidence_ids: set[str],
        quality_gate: PostQualityGate | None = None,
    ) -> Post | None:
        """
        Generate a post from a candidate and validate through the quality gate.

        If the quality gate fails:
        - The candidate remains in SELECTED status (recoverable)
        - No corrupt post is created
        - Returns None
        """
        if quality_gate is None:
            quality_gate = PostQualityGate()

        agent_res = await self.db.execute(
            select(Agent).options(selectinload(Agent.persona)).where(Agent.id == candidate.agent_id)
        )
        agent = agent_res.scalar_one_or_none()

        # Load the belief and its trigger evidence for rich context
        belief_res = await self.db.execute(
            select(Belief).where(Belief.id == candidate.belief_id)
        )
        belief = belief_res.scalar_one_or_none()
        belief_statement = belief.statement if belief else "N/A"

        from app.db.models import BeliefRevision, ResearchRun, Evidence
        rev_res = await self.db.execute(
            select(BeliefRevision)
            .options(selectinload(BeliefRevision.trigger_evidence))
            .where(BeliefRevision.id == candidate.revision_id)
        )
        rev = rev_res.scalar_one_or_none()
        trigger_evidence = rev.trigger_evidence.evidence_text if rev and rev.trigger_evidence else "N/A"

        run_res = await self.db.execute(
            select(ResearchRun)
            .where(ResearchRun.question_id == candidate.question_id)
            .order_by(ResearchRun.created_at.desc())
            .limit(1)
        )
        run = run_res.scalar_one_or_none()
        research_status = run.status if run else "UNKNOWN"

        valid_sources = ", ".join(known_evidence_ids) if known_evidence_ids else "None"
        prompt = (
            f"Write a comprehensive post based on this candidate. The post MUST be at least 150 characters long.\n"
            f"Persona Voice: {agent.persona.voice_style}\n"
            f"Headline: {candidate.headline}\n"
            f"Summary: {candidate.summary}\n"
            f"Underlying Belief: {belief_statement}\n"
            f"Current Belief Confidence: {belief.confidence if belief else 0.0}\n"
            f"Trigger Evidence Context: {trigger_evidence}\n"
            f"Research Status: {research_status}\n"
            f"Valid Source IDs: {valid_sources}\n"
            f"IMPORTANT: For 'source_ids', you MUST select ONLY from the Valid Source IDs provided above. Do not invent or hallucinate source IDs. If none are provided, use an empty list.\n"
            f"IMPORTANT: Do not conflate the magnitude of belief change with the absolute confidence level. Maintain appropriate uncertainty based on Current Belief Confidence.\n"
            f"IMPORTANT: If Research Status is PARTIAL, explicitly acknowledge that evidence is limited and avoid definitive or overly strong generalized claims.\n"
        )

        try:
            gen_post = await self.llm.generate_structured(prompt, GeneratedPost)

            # Fetch source URLs from IDs
            sources_list = []
            if gen_post.source_ids:
                sources_res = await self.db.execute(
                    select(Source)
                    .join(Evidence, Evidence.source_id == Source.id)
                    .where(Evidence.id.in_(gen_post.source_ids))
                )
                for src in sources_res.scalars().all():
                    sources_list.append(src.canonical_url)
                sources_list = list(set(sources_list))

            # ── Quality Gate ──────────────────────────────────────────────────
            text_lower = gen_post.text.lower()

            # Basic guardrails (kept from Phase 6)
            if "as an ai" in text_lower or "i am an ai" in text_lower:
                logger.warning("[EDITORIAL] Post rejected: contains AI placeholder")
                return None

            # Phase 7 quality gate
            result = quality_gate.validate(
                post_text=gen_post.text,
                source_ids=gen_post.source_ids or [],
                known_evidence_ids=known_evidence_ids,
                recent_post_texts=recent_post_texts,
            )
            if not result.passed:
                logger.warning(
                    f"[EDITORIAL] post_quality_failed reason={result.reason} "
                    f"candidate={candidate.id[:8]}"
                )
                # Candidate remains in SELECTED for retry — do NOT commit REJECTED
                return None

            # ── Construct post ────────────────────────────────────────────────
            rationale_json = gen_post.rationale.model_dump_json()

            # Atomic publication transition (Fix #4)
            from sqlalchemy import update
            result_update = await self.db.execute(
                update(EditorialCandidate)
                .where(EditorialCandidate.id == candidate.id)
                .where(EditorialCandidate.status.in_(["PENDING", "SELECTED"]))
                .values(status="PUBLISHED")
            )
            if result_update.rowcount == 0:
                logger.warning(f"[EDITORIAL] duplicate_publish_prevented candidate_id={candidate.id}")
                return None

            post = Post(
                id=str(uuid.uuid4()),
                agent_id=agent.id,
                text=gen_post.text,
                candidate_id=candidate.id,
                belief_id=candidate.belief_id,
                revision_id=candidate.revision_id,
                question_id=candidate.question_id,
                rationale=rationale_json,
                sources=sources_list
            )
            self.db.add(post)
            # The candidate is already marked PUBLISHED in the DB by the atomic update
            # We just update the local object for consistency
            candidate.status = "PUBLISHED"

            await self.db.commit()
            logger.info(f"[EDITORIAL] candidate_published candidate_id={candidate.id}")
            return post

        except Exception as e:
            logger.error(f"[EDITORIAL] Post generation failed: {e}")
            candidate.status = "FAILED"
            await self.db.commit()
            return None
