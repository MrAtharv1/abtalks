import pytest
import asyncio
from sqlalchemy.future import select
from app.db.models import Agent, PersonaProfile, ResearchThread, ResearchQuestion, Source, Evidence, Belief, BeliefRevision, BeliefEvidence
from app.memory.service import MemoryService
from app.memory.belief_engine import BeliefService, calculate_confidence_update
from app.llm.provider import FakeLLMProvider

@pytest.mark.asyncio
async def test_belief_engine_synthesis(db_session):
    # Setup Data
    persona = PersonaProfile(id="p_mem1", name="Tester", domain="Testing")
    agent = Agent(id="a_mem1", persona_id="p_mem1")
    thread = ResearchThread(id="t_mem1", agent_id="a_mem1", title="T1", description="D1")
    question = ResearchQuestion(id="q_mem1", thread_id="t_mem1", question="Q1")
    
    source = Source(id="s_mem1", url="http://test", canonical_url="http://test", quality_score=1.0)
    ev1 = Evidence(id="e_mem1", question_id="q_mem1", source_id="s_mem1", claim="C1", evidence_text="T1", relevance_score=1.0, source_quality_score=1.0, confidence=1.0, polarity="SUPPORTS")
    ev2 = Evidence(id="e_mem2", question_id="q_mem1", source_id="s_mem1", claim="C2", evidence_text="T2", relevance_score=1.0, source_quality_score=1.0, confidence=1.0, polarity="CONTRADICTS")
    
    db_session.add_all([persona, agent, thread, question, source, ev1, ev2])
    await db_session.commit()
    
    llm = FakeLLMProvider()
    engine = BeliefService(db_session, llm)
    
    beliefs = await engine.synthesize_for_question("q_mem1")
    
    assert len(beliefs) == 1
    belief = beliefs[0]
    assert belief.confidence == 0.6
    
    # FakeLLM assigns ev1 to supports, ev2 to contradicts based on regex ordering.
    links_res = await db_session.execute(select(BeliefEvidence).where(BeliefEvidence.belief_id == belief.id))
    links = links_res.scalars().all()
    assert len(links) == 2
    
    rev_res = await db_session.execute(select(BeliefRevision).where(BeliefRevision.belief_id == belief.id))
    revisions = rev_res.scalars().all()
    assert len(revisions) == 1
    assert revisions[0].change_type == "INITIAL"

@pytest.mark.asyncio
async def test_belief_engine_revision(db_session):
    # Setup Data
    persona = PersonaProfile(id="p_mem2", name="Tester", domain="Testing")
    agent = Agent(id="a_mem2", persona_id="p_mem2")
    thread = ResearchThread(id="t_mem2", agent_id="a_mem2", title="T2", description="D2")
    question = ResearchQuestion(id="q_mem2", thread_id="t_mem2", question="Q2")
    
    source = Source(id="s_mem2", url="http://test2", canonical_url="http://test2", quality_score=1.0)
    belief = Belief(id="b_mem2", agent_id="a_mem2", thread_id="t_mem2", statement="S", confidence=0.5, importance=0.8, status="ACTIVE")
    
    ev_new = Evidence(id="e_mem_new", question_id="q_mem2", source_id="s_mem2", claim="C", evidence_text="contradict", relevance_score=1.0, source_quality_score=1.0, confidence=1.0, polarity="CONTRADICTS")
    
    db_session.add_all([persona, agent, thread, question, source, belief, ev_new])
    await db_session.commit()
    
    llm = FakeLLMProvider()
    engine = BeliefService(db_session, llm)
    
    await engine.revise_beliefs("b_mem2", ["e_mem_new"])
    
    # FakeLLM will see "contradict" in the prompt from evidence text and return CONTRADICTS
    await db_session.refresh(belief)
    assert belief.confidence < 0.5 # 0.5 - (1.0*0.3) = 0.2
    
    rev_res = await db_session.execute(select(BeliefRevision).where(BeliefRevision.belief_id == belief.id))
    revisions = rev_res.scalars().all()
    assert len(revisions) == 1
    assert revisions[0].change_type == "WEAKENED"
    assert revisions[0].previous_confidence == 0.5
    assert revisions[0].new_confidence == pytest.approx(0.2)

@pytest.mark.asyncio
async def test_memory_service_isolation(db_session):
    # Create two agents with isolated beliefs
    p1 = PersonaProfile(id="p_mem1", name="Tester", domain="Testing")
    p2 = PersonaProfile(id="p_mem2", name="Tester", domain="Testing")
    a1 = Agent(id="a_m1", persona_id="p_mem1")
    a2 = Agent(id="a_m2", persona_id="p_mem2")
    t1 = ResearchThread(id="t_mem1", agent_id="a_m1", title="T1", description="D1")
    t2 = ResearchThread(id="t_mem2", agent_id="a_m2", title="T2", description="D2")
    
    b1 = Belief(id="b_1", agent_id="a_m1", thread_id="t_mem1", statement="B1", confidence=0.5, importance=0.5, status="ACTIVE")
    b2 = Belief(id="b_2", agent_id="a_m2", thread_id="t_mem2", statement="B2", confidence=0.5, importance=0.5, status="ACTIVE")
    
    db_session.add_all([p1, p2, a1, a2, t1, t2, b1, b2])
    await db_session.commit()
    
    mem = MemoryService(db_session)
    a1_beliefs = await mem.get_agent_beliefs("a_m1")
    assert len(a1_beliefs) == 1
    assert a1_beliefs[0].id == "b_1"
    
def test_confidence_math():
    # Supports: current + (weight * 0.2)
    assert calculate_confidence_update(0.5, 1.0, "SUPPORTS") == pytest.approx(0.7)
    # Contradicts: current - (weight * 0.3)
    assert calculate_confidence_update(0.5, 1.0, "CONTRADICTS") == pytest.approx(0.2)
    # Bounds checking
    assert calculate_confidence_update(0.9, 1.0, "SUPPORTS") == pytest.approx(0.99)
    assert calculate_confidence_update(0.1, 1.0, "CONTRADICTS") == pytest.approx(0.01)
