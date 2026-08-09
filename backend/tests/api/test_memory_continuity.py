import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.future import select
from app.db.database import AsyncSessionLocal
from app.db.models import Agent, ResearchThread, ResearchQuestion, Belief, Post, BeliefRevision, Evidence

@pytest.mark.asyncio
async def test_memory_continuity(client: AsyncClient, db_session):
    # This simulates the progression of memory over time.
    from app.llm.provider import FakeLLMProvider
    from app.editorial.service import EditorialService
    from app.memory.belief_engine import BeliefService
    from app.schemas.research import ExtractedEvidence
    from unittest.mock import patch
    
    agent_id = str(uuid.uuid4())
    thread_id = str(uuid.uuid4())
    question_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    
    # Setup persona, agent, thread, question
    from app.db.models import PersonaProfile
    persona_id = str(uuid.uuid4())
    db_session.add(PersonaProfile(id=persona_id, name="Ada", domain="Test", voice_style="test"))
    db_session.add(Agent(id=agent_id, persona_id=persona_id, status="ACTIVE"))
    db_session.add(ResearchThread(id=thread_id, agent_id=agent_id, title="Test Thread", description="Test"))
    db_session.add(ResearchQuestion(id=question_id, thread_id=thread_id, question="Is X true?"))
    await db_session.commit()
    
    llm = FakeLLMProvider()
    belief_svc = BeliefService(db_session, llm)
    editorial_svc = EditorialService(db_session, llm)
        
    # 1. Initial Evidence -> Form Belief
    ev1 = Evidence(
        id=str(uuid.uuid4()),
        question_id=question_id,
        source_id=source_id,
        claim="X is absolutely true.",
        evidence_text="Studies show X.",
        relevance_score=0.9,
        source_quality_score=0.9,
        confidence=0.8,
        polarity="SUPPORTS"
    )
    db_session.add(ev1)
    
    b1 = Belief(
        id=str(uuid.uuid4()),
        agent_id=agent_id,
        thread_id=thread_id,
        statement="X is true.",
        confidence=0.8,
        importance=0.8,
        status="ACTIVE"
    )
    db_session.add(b1)
    
    rev1 = BeliefRevision(
        id=str(uuid.uuid4()),
        belief_id=b1.id,
        previous_confidence=0.0,
        new_confidence=0.8,
        change_type="INITIAL",
        reason="Initial evidence supports X."
    )
    db_session.add(rev1)
    await db_session.commit()
    
    # 2. Editorial Engine publishes Post 1
    post1 = await editorial_svc.generate_next_editorial_item(agent_id)
    assert post1 is not None
    assert post1.belief_id == b1.id
    
    # Manually shift post1 back in time to guarantee ordering
    from datetime import datetime, timedelta
    post1.created_at = datetime.utcnow() - timedelta(minutes=5)
    
    # Bypass the editorial cooldown for the agent
    agent_res = await db_session.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_res.scalar_one_or_none()
    agent.last_post_at = post1.created_at
    await db_session.commit()
    
    # 3. New Contradicting Evidence -> Revise Belief
    ev2 = Evidence(
        id=str(uuid.uuid4()),
        question_id=question_id,
        source_id=source_id,
        claim="X is actually false.",
        evidence_text="New studies contradict X.",
        relevance_score=0.9,
        source_quality_score=0.9,
        confidence=0.9,
        polarity="CONTRADICTS"
    )
    db_session.add(ev2)
    await db_session.commit()
    
    await belief_svc.revise_beliefs(b1.id, [ev2.id])
    
    # Check that belief was revised
    b1_updated = await db_session.get(Belief, b1.id)
    assert b1_updated.confidence < 0.8
    assert b1_updated.status in ["WEAKENED", "DISPUTED"]
    
    # 4. Editorial Engine publishes Post 2 due to significant change
    post2 = await editorial_svc.generate_next_editorial_item(agent_id, belief_change_delta=0.5)
    
    assert post2 is not None
    assert post2.id != post1.id
    assert post2.belief_id == b1.id
    
    # Verify the feed output
    feed_res = await client.get(f"/api/agent/feed?agentId={agent_id}")
    feed_data = feed_res.json()
    assert len(feed_data["posts"]) == 2
    # newest first
    assert feed_data["posts"][0]["id"] == post2.id
    assert feed_data["posts"][1]["id"] == post1.id
