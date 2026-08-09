import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from app.db.models import Agent, PersonaProfile, ResearchThread, ResearchQuestion, AgentCycle, Belief, EditorialCandidate, Post
from app.runtime.agent_runtime import RuntimeManager
from app.runtime.scheduler import ResearchScheduler
from app.runtime.cycle import AgentCycleContext
from app.llm.provider import FakeLLMProvider
from app.research.search import FakeSearchProvider
from app.research.service import ResearchService
from app.memory.belief_engine import BeliefService
from app.editorial.service import EditorialService
from sqlalchemy.future import select

# A mocked fetcher for test isolation
class MockFetcher:
    async def fetch(self, url: str):
        class MockDoc:
            content_type = "text/html"
        return MockDoc()

class MockExtractor:
    def extract_text(self, doc):
        return "Grounded Claim Test Content with q1 and q2 keywords"

@pytest.fixture
def autonomous_services(db_session):
    llm = FakeLLMProvider()
    search = FakeSearchProvider()
    
    rs = ResearchService(db_session, llm, search)
    rs.fetcher = MockFetcher()
    rs.content_extractor = MockExtractor()
    
    bs = BeliefService(db_session, llm)
    es = EditorialService(db_session, llm)
    
    ctx = AgentCycleContext(db_session, rs, bs, es)
    return ctx

@pytest.mark.asyncio
async def test_scheduler_priority(db_session):
    # Setup
    persona = PersonaProfile(id="p_sch", name="Ada", domain="Test")
    agent = Agent(id="a_sch", persona_id="p_sch")
    thread = ResearchThread(id="t_sch", agent_id="a_sch", title="T1", description="D1", priority=1.0)
    
    # Q1: Highly uncertain (confidence 0.1), no cooldown
    q1 = ResearchQuestion(id="q1", thread_id="t_sch", question="Q1", importance=1.0, confidence=0.1)
    
    # Q2: High confidence (0.9) - should have anti-confirmation bias kick in
    q2 = ResearchQuestion(id="q2", thread_id="t_sch", question="Q2", importance=1.0, confidence=0.9)
    
    db_session.add_all([persona, agent, thread, q1, q2])
    await db_session.commit()
    
    scheduler = ResearchScheduler(db_session)
    next_q = await scheduler.select_next_question("a_sch")
    
    # Q1 score: 1.0 (thread) * 1.0 (imp) * 0.9 (uncert) * 2.0 (fresh) = 1.8
    # Q2 score: 1.0 (thread) * 1.0 (imp) * 0.5 (uncert via bias) * 2.0 (fresh) = 1.0
    assert next_q is not None
    assert next_q.id == "q1"

@pytest.mark.asyncio
async def test_autonomous_agent_lifecycle(db_session, autonomous_services):
    # Setup agent
    persona = PersonaProfile(id="p_auto1", name="Ada", domain="Test")
    agent = Agent(id="a_auto1", persona_id="p_auto1")
    thread = ResearchThread(id="t_auto1", agent_id="a_auto1", title="T1", description="D1", priority=1.0)
    q1 = ResearchQuestion(id="q_auto1", thread_id="t_auto1", question="Q1", importance=1.0, confidence=0.5)
    
    db_session.add_all([persona, agent, thread, q1])
    await db_session.commit()
    
    # Run cycle 1 (Should synthesize beliefs, no candidates yet since no revision delta maybe? Actually initial synthesis creates a revision)
    await autonomous_services.run_cycle("a_auto1")
    
    # Verify Cycle recorded
    cycle_res = await db_session.execute(select(AgentCycle).where(AgentCycle.agent_id == "a_auto1"))
    cycles = cycle_res.scalars().all()
    assert len(cycles) == 1
    assert cycles[0].status == "COMPLETED"
    
    # Verify Beliefs Created
    beliefs_res = await db_session.execute(select(Belief).where(Belief.agent_id == "a_auto1"))
    beliefs = beliefs_res.scalars().all()
    assert len(beliefs) > 0
    
    # Verify Post potentially created (EditorialEngine selects from initial revision)
    posts_res = await db_session.execute(select(Post).where(Post.agent_id == "a_auto1"))
    posts = posts_res.scalars().all()
    # Depending on FakeLLM thresholds, might be 0 or 1. Let's just ensure it doesn't crash.
    
@pytest.mark.asyncio
async def test_autonomous_belief_revision_cycle(db_session, autonomous_services):
    persona = PersonaProfile(id="p_auto2", name="Ada", domain="Test")
    agent = Agent(id="a_auto2", persona_id="p_auto2")
    thread = ResearchThread(id="t_auto2", agent_id="a_auto2", title="T1", description="D1", priority=1.0)
    q1 = ResearchQuestion(id="q_auto2", thread_id="t_auto2", question="Q1", importance=1.0)
    db_session.add_all([persona, agent, thread, q1])
    await db_session.commit()
    
    # Cycle 1: Search provider returns "supporting" evidence (call_count 1-3)
    await autonomous_services.run_cycle("a_auto2")
    beliefs_res = await db_session.execute(select(Belief).where(Belief.agent_id == "a_auto2"))
    initial_beliefs = beliefs_res.scalars().all()
    assert len(initial_beliefs) > 0
    initial_conf = initial_beliefs[0].confidence
    
    # Bypass cooldown for test
    thread.last_activity_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await db_session.commit()
    
    # Cycle 2: Search provider returns "contradictory" evidence (call_count > 3 via FakeLLMProvider/FakeSearchProvider)
    # The FakeSearchProvider has state, but since we recreate autonomous_services per test... wait, it's shared if we inject it.
    # Actually FakeSearchProvider is created inside fixture. Let's manually increment its state to force contradiction.
    autonomous_services.research_service.search_provider.call_count = 4
    
    await autonomous_services.run_cycle("a_auto2")
    
    await db_session.refresh(initial_beliefs[0])
    # The contradictory evidence should have lowered confidence and possibly spawned a post
    assert initial_beliefs[0].confidence < initial_conf
    assert initial_beliefs[0].status in ["WEAKENED", "DISPUTED", "ACTIVE"]

@pytest.mark.asyncio
async def test_runtime_survives_research_failure(db_session, autonomous_services):
    persona = PersonaProfile(id="p_auto3", name="Ada", domain="Test")
    agent = Agent(id="a_auto3", persona_id="p_auto3")
    thread = ResearchThread(id="t_auto3", agent_id="a_auto3", title="T1", description="D1")
    q1 = ResearchQuestion(id="q_auto3", thread_id="t_auto3", question="Q1")
    db_session.add_all([persona, agent, thread, q1])
    await db_session.commit()
    
    # Break the research service temporarily
    original_search = autonomous_services.research_service.search_provider
    class BrokenSearch:
        async def search(self, q, limit):
            raise ValueError("API Offline")
    autonomous_services.research_service.search_provider = BrokenSearch()
    
    # Should not throw, should record completed cycle (but run inside might be failed or completed with 0 results)
    await autonomous_services.run_cycle("a_auto3")
    
    cycle_res = await db_session.execute(select(AgentCycle).where(AgentCycle.agent_id == "a_auto3"))
    cycles = cycle_res.scalars().all()
    assert len(cycles) == 1
    assert cycles[0].status == "COMPLETED"
    
    # Restore and run again
    autonomous_services.research_service.search_provider = original_search
    thread.last_activity_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await db_session.commit()
    
    await autonomous_services.run_cycle("a_auto3")
    cycle_res = await db_session.execute(select(AgentCycle).where(AgentCycle.agent_id == "a_auto3").order_by(AgentCycle.started_at.desc()))
    cycles = cycle_res.scalars().all()
    assert cycles[0].status == "COMPLETED"

@pytest.mark.asyncio
async def test_duplicate_runtime_prevention():
    manager = RuntimeManager()
    
    # We don't want to actually run the loop, just check dictionary tracking
    manager.start("agent_x")
    assert "agent_x" in manager.active_tasks
    task1 = manager.active_tasks["agent_x"]
    
    # Start again, should not create a new task
    manager.start("agent_x")
    assert manager.active_tasks["agent_x"] is task1
    
    manager.stop("agent_x")
    assert "agent_x" not in manager.active_tasks

@pytest.mark.asyncio
async def test_shutdown_cleans_up():
    manager = RuntimeManager()
    manager.start("agent_y")
    manager.start("agent_z")
    
    assert len(manager.active_tasks) == 2
    
    await manager.shutdown_all()
    
    assert len(manager.active_tasks) == 0
