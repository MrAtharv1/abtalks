"""
EditorialService — orchestrates the editorial pipeline with Phase 7 enhancements:
    - Editorial cooldown: respects agent.last_post_at + editorial_min_interval
    - Exception: major belief reversals bypass cooldown
    - EditorialNoveltyChecker: blocks same-belief/same-question republishing
    - PostQualityGate: validates post before persistence
    - Accepts belief_change_delta from caller for cooldown bypass logic
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.config import settings
from app.llm.base import LLMProvider
from app.editorial.candidate import CandidateService
from app.editorial.scorer import ScorerService
from app.editorial.selector import SelectorService
from app.editorial.author import AuthorService
from app.editorial.novelty import EditorialNoveltyChecker
from app.editorial.quality_gate import PostQualityGate
from app.db.models import Post, Agent
import logging

logger = logging.getLogger("thread")


class EditorialService:
    def __init__(self, db: AsyncSession, llm: LLMProvider):
        self.db = db
        self.llm = llm
        self.candidate_service = CandidateService(db, llm)
        self.scorer_service = ScorerService(db)
        self.selector_service = SelectorService(db, threshold=settings.editorial_significance_threshold)
        self.author_service = AuthorService(db, llm)
        self.novelty_checker = EditorialNoveltyChecker(db, settings.editorial_major_change_threshold)
        self.quality_gate = PostQualityGate()

    async def generate_next_editorial_item(
        self,
        agent_id: str,
        belief_change_delta: float = 0.0,
    ) -> Post | None:
        """
        Main orchestration loop for editorial generation.

        Args:
            agent_id: The agent to generate for.
            belief_change_delta: The magnitude of belief change from the last cycle.
                                 Used to determine if editorial cooldown can be bypassed.
        """
        # ── 0. Editorial Cooldown Check ───────────────────────────────────────
        is_major_change = abs(belief_change_delta) >= settings.editorial_major_change_threshold
        
        agent_res = await self.db.execute(select(Agent).where(Agent.id == agent_id))
        agent = agent_res.scalar_one_or_none()

        if agent and agent.last_post_at and not is_major_change:
            last_post_at = agent.last_post_at
            if last_post_at.tzinfo is None:
                last_post_at = last_post_at.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - last_post_at).total_seconds()
            min_interval = settings.effective_editorial_min_interval
            if elapsed < min_interval:
                remaining = min_interval - elapsed
                logger.info(
                    f"[EDITORIAL] editorial_skipped reason=COOLDOWN "
                    f"remaining={remaining:.0f}s agent_id={agent_id}"
                )
                return None

        if is_major_change:
            logger.info(
                f"[EDITORIAL] Major belief change (delta={belief_change_delta:.3f}) "
                f"bypasses editorial cooldown"
            )

        # ── 1. Check for stranded SELECTED candidates ─────────────────────────
        from app.db.models import EditorialCandidate
        stranded_res = await self.db.execute(
            select(EditorialCandidate)
            .where(EditorialCandidate.agent_id == agent_id)
            .where(EditorialCandidate.status == "SELECTED")
            .outerjoin(Post, Post.candidate_id == EditorialCandidate.id)
            .where(Post.id == None)
            .limit(1)
        )
        stranded = stranded_res.scalar_one_or_none()

        if stranded:
            logger.info(f"[EDITORIAL] Retrying stranded candidate {stranded.id}")
            post = await self._author_with_quality_gate(
                stranded, agent_id, belief_change_delta
            )
            if post:
                await self._update_agent_post_time(agent_id)
            return post

        # ── 2. Generate Candidates ────────────────────────────────────────────
        candidates = await self.candidate_service.generate_candidates(agent_id)
        if not candidates:
            logger.info(f"[EDITORIAL] No new candidates generated for agent {agent_id}")
            return None

        # ── 3. Score Candidates ───────────────────────────────────────────────
        await self.scorer_service.score_candidates(candidates)

        # ── 4. Select Candidate ───────────────────────────────────────────────
        selected_candidate = await self.selector_service.select_candidate(candidates)
        if not selected_candidate:
            logger.info(f"[EDITORIAL] No candidate exceeded threshold for agent {agent_id}")
            return None

        # ── 5. Novelty check ──────────────────────────────────────────────────
        is_novel, novelty_reason = await self.novelty_checker.is_novel(
            agent_id=agent_id,
            belief_id=selected_candidate.belief_id,
            question_id=selected_candidate.question_id,
            belief_change_delta=belief_change_delta,
            source_domains=[],  # populated by author service if needed
        )

        if not is_novel:
            logger.info(
                f"[EDITORIAL] editorial_candidate_rejected "
                f"reason={novelty_reason} candidate={selected_candidate.id[:8]}"
            )
            selected_candidate.status = "REJECTED"
            selected_candidate.rejected_at = datetime.now(timezone.utc)
            await self.db.commit()
            return None

        # ── 6. Author Post with Quality Gate ─────────────────────────────────
        post = await self._author_with_quality_gate(
            selected_candidate, agent_id, belief_change_delta
        )
        if post:
            logger.info(
                f"[EDITORIAL] editorial_candidate_created "
                f"post_id={post.id[:8]} agent_id={agent_id}"
            )
            await self._update_agent_post_time(agent_id)
        else:
            logger.warning(
                f"[EDITORIAL] post_quality_failed candidate={selected_candidate.id[:8]}"
            )

        return post

    async def _author_with_quality_gate(
        self,
        candidate,
        agent_id: str,
        belief_change_delta: float,
    ) -> Post | None:
        """Author a post and validate it through the quality gate before persistence."""
        # Fetch recent posts for near-duplicate check
        recent_posts_res = await self.db.execute(
            select(Post)
            .where(Post.agent_id == agent_id)
            .order_by(Post.created_at.desc())
            .limit(5)
        )
        recent_post_texts = [p.text for p in recent_posts_res.scalars().all()]

        # Fetch known evidence IDs for source validation
        from app.db.models import Evidence
        evidence_res = await self.db.execute(
            select(Evidence.id)
            .where(Evidence.question_id == candidate.question_id)
            .limit(100)
        )
        known_evidence_ids = {row[0] for row in evidence_res.fetchall()}

        # Generate post (writes to DB only if quality gate passes)
        post = await self.author_service.generate_post_with_gate(
            candidate=candidate,
            recent_post_texts=recent_post_texts,
            known_evidence_ids=known_evidence_ids,
            quality_gate=self.quality_gate,
        )
        return post

    async def _update_agent_post_time(self, agent_id: str):
        """Update agent.last_post_at after a successful publish."""
        agent_res = await self.db.execute(select(Agent).where(Agent.id == agent_id))
        agent = agent_res.scalar_one_or_none()
        if agent:
            agent.last_post_at = datetime.now(timezone.utc)
            agent.total_posts = (agent.total_posts or 0) + 1
            await self.db.commit()
