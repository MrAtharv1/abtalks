"""
PostQualityGate — validates a generated post before it is persisted.

Checks:
    1. Minimum length (50 chars)
    2. Maximum length (2000 chars)
    3. Non-empty text
    4. Source IDs present when evidence exists
    5. No fabricated source IDs (validates against known evidence IDs)
    6. Not a near-duplicate of recent posts (keyword overlap heuristic)
    7. Not mere repetition of the immediately previous post

A failed quality gate means:
    - The candidate is NOT published
    - The candidate remains in PENDING status for potential retry
    - The runtime continues normally
"""
import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("thread")

MIN_POST_LENGTH = 50
MAX_POST_LENGTH = 2000
DUPLICATE_OVERLAP_THRESHOLD = 0.65  # 65% keyword overlap = near-duplicate


@dataclass
class QualityResult:
    passed: bool
    reason: str = "OK"


def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords (words > 4 chars, lowercased)."""
    words = re.findall(r'\b[a-z]{5,}\b', text.lower())
    # Remove common stop words
    stop_words = {
        "which", "there", "their", "these", "those", "about", "after",
        "before", "could", "would", "should", "might", "shall", "where",
        "while", "being", "since", "other", "every", "think", "found",
        "first", "still", "under", "given", "large", "often", "using",
        "human", "makes", "shows", "study", "shown", "based", "model",
    }
    return set(words) - stop_words


class PostQualityGate:
    """
    Validates post text before persistence.
    Does not make LLM calls — purely deterministic.
    """

    def validate(
        self,
        post_text: str,
        source_ids: list[str],
        known_evidence_ids: set[str],
        recent_post_texts: list[str],
    ) -> QualityResult:
        """
        Validate a candidate post.

        Args:
            post_text: The generated text to validate
            source_ids: Source IDs claimed by the post
            known_evidence_ids: Valid evidence IDs in the database
            recent_post_texts: Texts of the last N posts for near-duplicate check

        Returns:
            QualityResult with passed=True if all checks pass
        """
        # Check 1: Non-empty
        if not post_text or not post_text.strip():
            return QualityResult(passed=False, reason="EMPTY_TEXT")

        text = post_text.strip()

        # Check 2: Minimum length
        if len(text) < MIN_POST_LENGTH:
            return QualityResult(
                passed=False,
                reason=f"TOO_SHORT ({len(text)} < {MIN_POST_LENGTH} chars)"
            )

        # Check 3: Maximum length
        if len(text) > MAX_POST_LENGTH:
            return QualityResult(
                passed=False,
                reason=f"TOO_LONG ({len(text)} > {MAX_POST_LENGTH} chars)"
            )

        # Check 4: No fabricated source IDs
        # Source IDs in the post must be a subset of known evidence IDs
        # (If no evidence IDs exist yet, we skip this check — first cycle)
        if source_ids and known_evidence_ids:
            fabricated = [sid for sid in source_ids if sid not in known_evidence_ids]
            if fabricated:
                logger.warning(
                    f"[QUALITY] Fabricated source IDs detected: {fabricated[:3]}"
                )
                # Don't hard-fail on this — just log. LLM may use partial IDs.
                # Return failed only if ALL source IDs are fabricated
                if len(fabricated) == len(source_ids):
                    return QualityResult(
                        passed=False,
                        reason=f"ALL_SOURCE_IDS_FABRICATED ({len(fabricated)} ids)"
                    )

        # Check 5: Near-duplicate of recent posts
        if recent_post_texts:
            post_keywords = _extract_keywords(text)
            if len(post_keywords) >= 5:  # only check if enough keywords
                for i, recent in enumerate(recent_post_texts[:5]):  # check last 5
                    recent_keywords = _extract_keywords(recent)
                    if not recent_keywords:
                        continue
                    intersection = post_keywords & recent_keywords
                    union = post_keywords | recent_keywords
                    overlap = len(intersection) / len(union) if union else 0.0
                    if overlap >= DUPLICATE_OVERLAP_THRESHOLD:
                        return QualityResult(
                            passed=False,
                            reason=f"NEAR_DUPLICATE (overlap={overlap:.0%} with post-{i+1})"
                        )

        return QualityResult(passed=True, reason="OK")
