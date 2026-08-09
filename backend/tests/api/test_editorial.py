import pytest
import uuid
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from httpx import AsyncClient

from app.db.models import Agent, PersonaProfile, ResearchThread, ResearchQuestion, Evidence, Belief, BeliefRevision, EditorialCandidate, EditorialDecision, Post
from app.editorial.candidate import CandidateService
from app.editorial.scorer import ScorerService
from app.editorial.selector import SelectorService
from app.editorial.author import AuthorService
from app.editorial.service import EditorialService
from app.llm.provider import FakeLLMProvider

async def setup_editorial_data(db_session):
    agent_id = str(uuid.uuid4())
    persona_id = str(uuid.uuid4())
    thread_id = str(uuid.uuid4())
    q_id = str(uuid.uuid4())
    ev_id = str(uuid.uuid4())
    belief_id = str(uuid.uuid4())
    rev_id = str(uuid.uuid4())
    
    p = PersonaProfile(id=persona_id, name="Ada", domain="Test")
    a = Agent(id=agent_id, persona_id=persona_id)
    t = ResearchThread(id=thread_id, agent_id=agent_id, title="T1", description="D1")
    q = ResearchQuestion(id=q_id, thread_id=thread_id, question="Q1")
    e = Evidence(id=ev_id, question_id=q_id, source_id="src1", claim="C1", evidence_text="E1", relevance_score=1.0, source_quality_score=1.0, confidence=1.0, polarity="SUPPORTS")
    b = Belief(id=belief_id, agent_id=agent_id, thread_id=thread_id, statement="B1", confidence=0.8, importance=0.8, status="ACTIVE")
    rev = BeliefRevision(
        id=rev_id,
        belief_id=belief_id,
        previous_confidence=0.5,
        new_confidence=0.8,
        change_type="INITIAL",
        reason="Test",
        trigger_evidence_id=ev_id
    )
    
    db_session.add_all([p, a, t, q, e, b, rev])
    await db_session.commit()
    
    return {
        "agent_id": agent_id,
        "belief_id": belief_id,
        "rev_id": rev_id,
        "ev_id": ev_id
    }

@pytest.mark.asyncio
async def test_candidate_generation(db_session):
    data = await setup_editorial_data(db_session)
    agent_id = data["agent_id"]
    llm = FakeLLMProvider()
    svc = CandidateService(db_session, llm)
    
    cands = await svc.generate_candidates(agent_id)
    assert len(cands) == 1
    assert cands[0].status == "PENDING"
    assert cands[0].belief_id == data["belief_id"]
    assert cands[0].revision_id == data["rev_id"]

@pytest.mark.asyncio
async def test_duplicate_prevention_same_revision(db_session):
    data = await setup_editorial_data(db_session)
    agent_id = data["agent_id"]
    llm = FakeLLMProvider()
    svc = CandidateService(db_session, llm)
    
    cands1 = await svc.generate_candidates(agent_id)
    assert len(cands1) == 1
    
    cands2 = await svc.generate_candidates(agent_id)
    assert len(cands2) == 0 # Already has a candidate

@pytest.mark.asyncio
async def test_scorer_logic(db_session):
    data = await setup_editorial_data(db_session)
    agent_id = data["agent_id"]
    llm = FakeLLMProvider()
    cand_svc = CandidateService(db_session, llm)
    scorer = ScorerService(db_session)
    
    cands = await cand_svc.generate_candidates(agent_id)
    await scorer.score_candidates(cands)
    
    cand = cands[0]
    assert cand.competition_score > 0
    # belief change 0.8 - 0.5 = 0.3 => 0.25 * 0.3 = 0.075 + other defaults

@pytest.mark.asyncio
async def test_repetition_penalty(db_session):
    data = await setup_editorial_data(db_session)
    agent_id = data["agent_id"]
    llm = FakeLLMProvider()
    
    # Simulate a prior post for this belief
    p = Post(id="post1", agent_id=agent_id, text="Prior", belief_id=data["belief_id"])
    db_session.add(p)
    await db_session.commit()
    
    cand_svc = CandidateService(db_session, llm)
    scorer = ScorerService(db_session)
    
    cands = await cand_svc.generate_candidates(agent_id)
    await scorer.score_candidates(cands)
    
    cand = cands[0]
    assert cand.novelty_score < 1.0 # Penalized

@pytest.mark.asyncio
async def test_selector_logic(db_session):
    data = await setup_editorial_data(db_session)
    agent_id = data["agent_id"]
    llm = FakeLLMProvider()
    cand_svc = CandidateService(db_session, llm)
    scorer = ScorerService(db_session)
    selector = SelectorService(db_session, threshold=0.1) # low threshold
    
    cands = await cand_svc.generate_candidates(agent_id)
    await scorer.score_candidates(cands)
    
    selected = await selector.select_candidate(cands)
    assert selected is not None
    assert selected.status == "SELECTED"
    
    decisions = await db_session.execute(select(EditorialDecision).where(EditorialDecision.candidate_id == selected.id))
    dec = decisions.scalar_one_or_none()
    assert dec is not None
    assert dec.decision_type == "SELECTED"

@pytest.mark.asyncio
async def test_author_post_generation(db_session):
    data = await setup_editorial_data(db_session)
    agent_id = data["agent_id"]
    llm = FakeLLMProvider()
    cand_svc = CandidateService(db_session, llm)
    scorer = ScorerService(db_session)
    selector = SelectorService(db_session, threshold=0.1)
    author = AuthorService(db_session, llm)
    
    cands = await cand_svc.generate_candidates(agent_id)
    await scorer.score_candidates(cands)
    selected = await selector.select_candidate(cands)
    
    post = await author.generate_post(selected)
    assert post is not None
    assert post.candidate_id == selected.id
    assert post.rationale is not None
    assert selected.status == "PUBLISHED"

@pytest.mark.asyncio
async def test_editorial_service_orchestration(db_session):
    data = await setup_editorial_data(db_session)
    agent_id = data["agent_id"]
    llm = FakeLLMProvider()
    svc = EditorialService(db_session, llm)
    svc.selector_service.threshold = 0.1 # Ensure it passes
    
    post = await svc.generate_next_editorial_item(agent_id)
    assert post is not None
    assert "fake generated post" in post.text.lower()
    
    # Calling again should yield None because no new revisions
    post2 = await svc.generate_next_editorial_item(agent_id)
    assert post2 is None

@pytest.mark.asyncio
async def test_low_significance_suppression(db_session):
    data = await setup_editorial_data(db_session)
    agent_id = data["agent_id"]
    llm = FakeLLMProvider()
    svc = EditorialService(db_session, llm)
    svc.selector_service.threshold = 0.99 # Unattainable threshold
    
    post = await svc.generate_next_editorial_item(agent_id)
    assert post is None # Should be suppressed

@pytest.mark.asyncio
async def test_feed_endpoint(client: AsyncClient, setup_db):
    # Same as orchestration test, but via API
    from tests.conftest import TestingSessionLocal
    llm = FakeLLMProvider()
    
    async with TestingSessionLocal() as db:
        agent_id = str(uuid.uuid4())
        p = PersonaProfile(id=str(uuid.uuid4()), name="Ada", domain="Test")
        a = Agent(id=agent_id, persona_id=p.id)
        b = Belief(id=str(uuid.uuid4()), agent_id=agent_id, thread_id=str(uuid.uuid4()), statement="B", confidence=0.5, importance=0.5, status="ACTIVE")
        rev = BeliefRevision(id=str(uuid.uuid4()), belief_id=b.id, previous_confidence=0.1, new_confidence=0.9, change_type="INITIAL", reason="Test")
        db.add_all([p, a, b, rev])
        await db.commit()
        
        svc = EditorialService(db, llm)
        svc.selector_service.threshold = 0.1
        await svc.generate_next_editorial_item(agent_id)
        
    response = await client.get(f"/api/agent/feed?agentId={agent_id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data["posts"]) == 1
    assert "rationale" in data["posts"][0]
    assert "sources" in data["posts"][0]
    # Check that rationale was unpacked correctly - it's a JSON string in DB, but the API might return it as a string
    # Actually the schema says `rationale: Optional[str]`, so it's a string.
    assert "why_selected" in data["posts"][0]["rationale"]
