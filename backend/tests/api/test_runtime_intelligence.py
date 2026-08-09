"""
Tests for Phase 7 runtime intelligence:
- ResearchOpportunityGate
- PostQualityGate
- EditorialNoveltyChecker
- ResearchYieldTracker (via mocked DB)
- State machine transitions
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.runtime.opportunity import ResearchOpportunityGate, GateDecision
from app.editorial.quality_gate import PostQualityGate
from app.runtime.state import AgentRuntimeState, RuntimeStateRegistry


# ─────────────────────────────────────────────────────────────
#  ResearchOpportunityGate
# ─────────────────────────────────────────────────────────────

def make_question(
    importance=0.8,
    confidence=0.5,
    yield_score=0.5,
    research_attempts=0,
    consecutive_low_yield=0,
    stagnant_until=None,
    last_activity_at=None,
    thread_priority=0.8,
):
    """Create a mock ResearchQuestion with all Phase 7 fields."""
    q = MagicMock()
    q.id = "test-question-id-1234"
    q.question = "What are the main risks of autonomous AI systems?"
    q.importance = importance
    q.confidence = confidence
    q.yield_score = yield_score
    q.research_attempts = research_attempts
    q.consecutive_low_yield_runs = consecutive_low_yield
    q.useful_evidence_count = 3
    q.stagnant_until = stagnant_until

    thread = MagicMock()
    thread.priority = thread_priority
    thread.last_activity_at = last_activity_at
    q.thread = thread

    return q


def test_gate_passes_fresh_question():
    gate = ResearchOpportunityGate()
    q = make_question()
    decision = gate.evaluate(q)
    assert decision.should_research is True
    assert decision.reason == "ELIGIBLE"
    assert decision.score > 0


def test_gate_rejects_stagnant_question():
    gate = ResearchOpportunityGate()
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    q = make_question(stagnant_until=future)
    decision = gate.evaluate(q)
    assert decision.should_research is False
    assert "STAGNANT" in decision.reason


def test_gate_passes_question_after_stagnant_cooldown_expires():
    gate = ResearchOpportunityGate()
    past = datetime.now(timezone.utc) - timedelta(hours=1)  # Expired stagnation
    q = make_question(stagnant_until=past)
    decision = gate.evaluate(q)
    assert decision.should_research is True


def test_gate_rejects_question_in_cooldown():
    gate = ResearchOpportunityGate()
    # Just researched 30 seconds ago
    recent = datetime.now(timezone.utc) - timedelta(seconds=30)
    q = make_question(last_activity_at=recent)
    decision = gate.evaluate(q)
    # research_cooldown_seconds defaults to 60s, so 30s ago should be blocked
    assert decision.should_research is False
    assert "COOLDOWN" in decision.reason


def test_gate_scores_high_uncertainty_higher():
    gate = ResearchOpportunityGate()
    q_certain = make_question(confidence=0.9)  # high confidence, low uncertainty
    q_uncertain = make_question(confidence=0.2)  # low confidence, high uncertainty

    d_certain = gate.evaluate(q_certain)
    d_uncertain = gate.evaluate(q_uncertain)

    assert d_uncertain.score > d_certain.score


def test_gate_prefers_never_researched_question():
    gate = ResearchOpportunityGate()
    q_fresh = make_question(research_attempts=0, last_activity_at=None)
    q_old = make_question(
        research_attempts=5,
        importance=0.8,
        confidence=0.5,
        last_activity_at=datetime.now(timezone.utc) - timedelta(seconds=120)
    )

    d_fresh = gate.evaluate(q_fresh)
    d_old = gate.evaluate(q_old)

    # Fresh (never researched) should always pass gate
    assert d_fresh.should_research is True
    # Fresh should score at least as well as the recently-researched one
    # (freshness=2.0 vs freshness based on delta)
    assert d_fresh.score >= d_old.score or not d_old.should_research


def test_gate_rank_returns_sorted_list():
    gate = ResearchOpportunityGate()
    q1 = make_question(importance=0.9, confidence=0.2)
    q2 = make_question(importance=0.3, confidence=0.8)
    ranked = gate.rank_questions([q1, q2])
    assert len(ranked) >= 1
    # First should have higher score
    if len(ranked) == 2:
        assert ranked[0][0] >= ranked[1][0]


def test_gate_rank_excludes_stagnant():
    gate = ResearchOpportunityGate()
    q_ok = make_question()
    q_stagnant = make_question(stagnant_until=datetime.now(timezone.utc) + timedelta(hours=1))
    q_stagnant.id = "stagnant-question-id-xyz"  # Distinct ID
    ranked = gate.rank_questions([q_ok, q_stagnant])
    # Stagnant question should not appear in ranked results
    ranked_ids = [q.id for _, q in ranked]
    assert "stagnant-question-id-xyz" not in ranked_ids


# ─────────────────────────────────────────────────────────────
#  PostQualityGate
# ─────────────────────────────────────────────────────────────

def make_gate():
    return PostQualityGate()


def test_quality_gate_passes_valid_post():
    gate = make_gate()
    result = gate.validate(
        post_text="AI security researchers have identified new vulnerabilities in large language models deployed in production. The attack surface includes prompt injection, jailbreaking techniques, and model inversion attacks that can extract training data.",
        source_ids=[],
        known_evidence_ids=set(),
        recent_post_texts=[],
    )
    assert result.passed is True


def test_quality_gate_rejects_empty_post():
    gate = make_gate()
    result = gate.validate("", [], set(), [])
    assert result.passed is False
    assert "EMPTY" in result.reason


def test_quality_gate_rejects_too_short():
    gate = make_gate()
    result = gate.validate("Too short.", [], set(), [])
    assert result.passed is False
    assert "TOO_SHORT" in result.reason


def test_quality_gate_rejects_too_long():
    gate = make_gate()
    long_text = "x" * 2500
    result = gate.validate(long_text, [], set(), [])
    assert result.passed is False
    assert "TOO_LONG" in result.reason


def test_quality_gate_rejects_near_duplicate():
    gate = make_gate()
    original = "The artificial intelligence security landscape reveals multiple concerning developments including adversarial attacks on machine learning systems and prompt injection vulnerabilities."
    near_dup = "The artificial intelligence security landscape reveals multiple concerning developments including adversarial attacks on machine learning systems and prompt injection vulnerabilities, with new findings from researchers."
    result = gate.validate(near_dup, [], set(), [original])
    assert result.passed is False
    assert "NEAR_DUPLICATE" in result.reason


def test_quality_gate_passes_genuinely_different_post():
    gate = make_gate()
    post1 = "Quantum computing poses significant challenges for current encryption standards, particularly RSA and ECC algorithms used in financial systems."
    post2 = "Autonomous vehicle safety regulations have undergone significant revisions following incidents involving sensor failures in adverse weather conditions."
    result = gate.validate(post2, [], set(), [post1])
    assert result.passed is True


def test_quality_gate_rejects_all_fabricated_source_ids():
    gate = make_gate()
    result = gate.validate(
        post_text="According to the research, autonomous AI systems require careful oversight mechanisms to prevent unintended consequences in deployment scenarios.",
        source_ids=["fake-id-1", "fake-id-2"],
        known_evidence_ids={"real-id-1", "real-id-2"},
        recent_post_texts=[],
    )
    assert result.passed is False
    assert "FABRICATED" in result.reason


def test_quality_gate_accepts_partial_known_sources():
    gate = make_gate()
    result = gate.validate(
        post_text="Research demonstrates that machine learning models can be manipulated through carefully crafted input patterns, raising concerns about deployment in high-stakes applications.",
        source_ids=["real-id-1", "fake-id-2"],
        known_evidence_ids={"real-id-1", "real-id-2"},  # one matches
        recent_post_texts=[],
    )
    # Only fails if ALL source IDs are fabricated
    assert result.passed is True


# ─────────────────────────────────────────────────────────────
#  RuntimeStateMachine
# ─────────────────────────────────────────────────────────────

def test_state_machine_initial_state_is_stopped():
    state = AgentRuntimeState("agent-1")
    assert state.state == "STOPPED"


def test_state_machine_valid_transition():
    state = AgentRuntimeState("agent-1")
    result = state.transition("STARTING")
    assert result is True
    assert state.state == "STARTING"


def test_state_machine_invalid_transition_returns_false():
    state = AgentRuntimeState("agent-1")
    result = state.transition("RUNNING")  # Can't go STOPPED → RUNNING
    assert result is False
    assert state.state == "STOPPED"


def test_state_machine_records_cycle_stats():
    state = AgentRuntimeState("agent-1")
    state.record_cycle_success()
    state.record_cycle_success()
    state.record_cycle_failure()
    dash = state.dashboard()
    assert dash["cycles_completed"] == 2
    assert dash["cycles_failed"] == 1


def test_state_machine_records_post_published():
    state = AgentRuntimeState("agent-1")
    state.record_post_published()
    dash = state.dashboard()
    assert dash["posts_created"] == 1
    assert dash["last_post_at"] is not None


def test_state_registry_creates_unique_states():
    registry = RuntimeStateRegistry()
    s1 = registry.get_or_create("agent-A")
    s2 = registry.get_or_create("agent-B")
    assert s1 is not s2


def test_state_registry_returns_same_instance():
    registry = RuntimeStateRegistry()
    s1 = registry.get_or_create("agent-X")
    s2 = registry.get_or_create("agent-X")
    assert s1 is s2


def test_state_machine_dashboard_includes_all_fields():
    state = AgentRuntimeState("agent-1")
    dash = state.dashboard()
    expected_keys = [
        "agent_id", "state", "cycles_completed", "cycles_failed",
        "posts_created", "consecutive_failures", "budget", "cadence"
    ]
    for key in expected_keys:
        assert key in dash, f"Missing key: {key}"
