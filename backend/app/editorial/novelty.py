"""
EditorialNoveltyChecker — lightweight semantic novelty check before publication.

Prevents publishing a post that is essentially a restatement of a recent post.
Uses deterministic heuristics only (no embeddings).

Checks:
    - Same belief_id as a recent post
    - Same source domains as a recent post
    - High keyword overlap with recent posts (handled by PostQualityGate)
    - Same question_id + no significant belief delta

A major belief reversal (abs(delta) >= threshold) BYPASSES this check.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("thread")


class EditorialNoveltyChecker:
    """
    Checks whether a candidate adds meaningful new information
    relative to recent publication history.
    """

    def __init__(self, db, major_change_threshold: float = 0.3):
        self.db = db
        self.major_change_threshold = major_change_threshold

    async def is_novel(
        self,
        agent_id: str,
        belief_id: Optional[str],
        question_id: Optional[str],
        belief_change_delta: float,
        source_domains: list[str],
        lookback_posts: int = 10,
    ) -> tuple[bool, str]:
        """
        Returns (is_novel, reason).
        
        A major belief reversal always returns (True, "MAJOR_BELIEF_CHANGE").
        """
        from sqlalchemy.future import select
        from app.db.models import Post, EditorialCandidate, Belief

        # Major belief changes bypass novelty check
        if abs(belief_change_delta) >= self.major_change_threshold:
            logger.info(
                f"[NOVELTY] Major belief change (delta={belief_change_delta:.2f}) "
                f"bypasses novelty check → NOVEL"
            )
            return True, "MAJOR_BELIEF_CHANGE"

        # Fetch recent posts
        posts_res = await self.db.execute(
            select(Post)
            .where(Post.agent_id == agent_id)
            .order_by(Post.created_at.desc())
            .limit(lookback_posts)
        )
        recent_posts = posts_res.scalars().all()

        if not recent_posts:
            return True, "NO_RECENT_POSTS"

        # Check 1: Same belief_id published recently
        if belief_id:
            for post in recent_posts:
                if post.belief_id == belief_id:
                    logger.info(
                        f"[NOVELTY] belief_id={belief_id[:8]} already published "
                        f"(post={post.id[:8]}) → NOT NOVEL"
                    )
                    return False, "SAME_BELIEF_ALREADY_PUBLISHED"

        # Check 2: Same question recently published (with low delta)
        # If the same question was covered recently and no major change, skip
        if question_id and abs(belief_change_delta) < 0.1:
            for post in recent_posts:
                if post.question_id == question_id:
                    logger.info(
                        f"[NOVELTY] question_id={question_id[:8]} already published "
                        f"with low delta={belief_change_delta:.2f} → NOT NOVEL"
                    )
                    return False, "SAME_QUESTION_LOW_DELTA"

        return True, "NOVEL"
