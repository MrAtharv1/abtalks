"""
ResearchOpportunityGate — deterministic pre-cycle gate.

Decides whether to spend research budget on a given question.
Zero LLM calls. Purely algorithmic.

Score formula:
    score = importance × uncertainty × yield_multiplier × freshness × contradiction_bonus

Where:
    importance        = question.importance (0–1)
    uncertainty       = 1 - question.confidence, with anti-confirmation bias at 0.85+
    yield_multiplier  = derived from question.yield_score (higher yield history → higher)
    freshness         = time-based multiplier (longer since last research → higher)
    contradiction_bonus = extra weight if question has produced contradictions before
"""
import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional

from app.config import settings

logger = logging.getLogger("thread")


@dataclass
class GateDecision:
    should_research: bool
    reason: str
    score: float = 0.0
    question_id: Optional[str] = None
    question_text: Optional[str] = None


class ResearchOpportunityGate:
    """
    Pre-cycle gate that evaluates whether a question is worth researching.
    Accepts a ResearchQuestion ORM object and returns a GateDecision.
    """

    def evaluate(self, question, now: datetime | None = None) -> GateDecision:
        """
        Evaluate a single question for research eligibility.

        Returns GateDecision with should_research=True if the question
        passes all gates and has a meaningful score.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        qid = question.id
        qtext = question.question[:80]

        # Gate 1: Stagnation check
        stagnant_until = getattr(question, "stagnant_until", None)
        if stagnant_until is not None:
            # Normalize timezone
            if stagnant_until.tzinfo is None:
                stagnant_until = stagnant_until.replace(tzinfo=timezone.utc)
            if now < stagnant_until:
                remaining = (stagnant_until - now).total_seconds() / 60
                return GateDecision(
                    should_research=False,
                    reason=f"STAGNANT (cooldown {remaining:.0f}min remaining)",
                    question_id=qid,
                    question_text=qtext,
                )

        # Gate 2: Thread-level cooldown (uses thread.last_activity_at)
        thread = question.thread
        if thread and thread.last_activity_at:
            activity_time = thread.last_activity_at
            if activity_time.tzinfo is None:
                activity_time = activity_time.replace(tzinfo=timezone.utc)
            delta_seconds = (now - activity_time).total_seconds()
            if delta_seconds < settings.research_cooldown_seconds:
                return GateDecision(
                    should_research=False,
                    reason=f"COOLDOWN ({settings.research_cooldown_seconds - delta_seconds:.0f}s remaining)",
                    question_id=qid,
                    question_text=qtext,
                )

        # Compute score
        score = self._compute_score(question, now)

        # Gate 3: Minimum score threshold (avoid near-zero-value research)
        if score < 0.05:
            return GateDecision(
                should_research=False,
                reason=f"LOW_SCORE ({score:.3f} < 0.05)",
                score=score,
                question_id=qid,
                question_text=qtext,
            )

        return GateDecision(
            should_research=True,
            reason="ELIGIBLE",
            score=score,
            question_id=qid,
            question_text=qtext,
        )

    def _compute_score(self, question, now: datetime) -> float:
        """
        Compute the expected information value for a research question.
        All factors are 0..1 or multipliers.
        """
        # Importance
        importance = max(0.0, min(1.0, question.importance))

        # Uncertainty (with anti-confirmation bias)
        conf = question.confidence
        if conf >= 0.85:
            uncertainty = 0.5   # challenge high-confidence beliefs
        else:
            uncertainty = 1.0 - conf
        uncertainty = max(0.01, uncertainty)

        # Yield multiplier from historical research performance
        yield_score = getattr(question, "yield_score", 0.5)
        if yield_score is None:
            yield_score = 0.5
        # If question has never been researched, assume moderate yield
        attempts = getattr(question, "research_attempts", 0) or 0
        if attempts == 0:
            yield_multiplier = 1.0  # unknown → assume valuable
        else:
            # Higher historical yield → higher multiplier (0.3..1.5)
            yield_multiplier = 0.3 + (yield_score * 1.2)

        # Freshness (time since last research)
        thread = question.thread
        freshness = 2.0  # never researched = high freshness
        if thread and thread.last_activity_at:
            activity_time = thread.last_activity_at
            if activity_time.tzinfo is None:
                activity_time = activity_time.replace(tzinfo=timezone.utc)
            delta_hours = (now - activity_time).total_seconds() / 3600.0
            # Cap at 5.0 — diminishing returns on staleness
            freshness = min(5.0, max(0.1, delta_hours))

        # Thread priority
        thread_priority = getattr(thread, "priority", 0.5) or 0.5

        # Contradiction bonus — questions that have produced contradictions before
        # are more epistemically valuable to re-examine
        contradictory_count = getattr(question, "useful_evidence_count", 0) or 0
        useful_count = getattr(question, "useful_evidence_count", 0) or 0
        # Simple bonus: more useful evidence history → more worth revisiting
        contradiction_bonus = 1.0 + min(0.5, useful_count * 0.1)

        score = (
            importance
            * uncertainty
            * yield_multiplier
            * (freshness / 5.0)  # normalize to 0..1 range
            * thread_priority
            * contradiction_bonus
        )

        return max(0.0, min(10.0, score))  # unbounded top end is fine for ranking

    def rank_questions(self, questions: list, now: datetime | None = None) -> list[tuple]:
        """
        Evaluate and rank a list of questions by score.
        Returns list of (score, question) tuples, descending.
        Only includes questions that pass the gate.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        ranked = []
        for q in questions:
            decision = self.evaluate(q, now)
            if decision.should_research:
                ranked.append((decision.score, q))
            else:
                logger.debug(
                    f"[GATE] question_rejected id={q.id[:8]} reason={decision.reason}"
                )

        ranked.sort(key=lambda x: x[0], reverse=True)
        return ranked
