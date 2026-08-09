import pytest
import asyncio
from app.research.search import FakeSearchProvider
from app.research.query_planner import QueryPlanner
from app.research.evidence import EvidenceExtractor
from app.research.service import ResearchService
from app.llm.provider import FakeLLMProvider
from app.schemas.research import FetchedDocument, ExtractedEvidence
from app.db.models import Agent, PersonaProfile, ResearchThread, ResearchQuestion, ResearchRun, Source, Evidence
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

# A mocked fetcher to avoid internet access during tests
class MockFetcher:
    async def fetch(self, url: str) -> FetchedDocument:
        if "fail" in url:
            raise ValueError("Simulated fetch failure")
        return FetchedDocument(
            url=url,
            final_url=url,
            content_type="text/html",
            raw_content=b"<html><body><p>Grounded Claim Test Content with answer</p></body></html>",
            title="Test Doc"
        )

@pytest.fixture
def mock_fetcher():
    return MockFetcher()

@pytest.mark.asyncio
async def test_query_planner(db_session):
    llm = FakeLLMProvider()
    planner = QueryPlanner(llm)
    
    question = ResearchQuestion(id="q1", question="How does this work?", thread_id="t1")
    persona = PersonaProfile(id="p1", name="Ada", domain="Security")
    
    queries = await planner.generate_queries(question, persona)
    assert len(queries.queries) == 2
    assert queries.queries[0].angle == "OVERVIEW"

@pytest.mark.asyncio
async def test_evidence_grounding():
    llm = FakeLLMProvider()
    extractor = EvidenceExtractor(llm)
    
    ev = ExtractedEvidence(
        claim="Test",
        evidence_text="Grounded Claim Test Content with answer",
        context="Ctx",
        relevance_score=0.9,
        confidence=0.8,
        polarity="SUPPORTS"
    )
    
    source_text = "Here is some Grounded Claim Test Content with answer that we found."
    assert extractor.check_grounding(ev, source_text) is True
    
    source_text_bad = "This has nothing to do with it."
    assert extractor.check_grounding(ev, source_text_bad) is False

@pytest.mark.asyncio
async def test_research_service_full_run(db_session, mock_fetcher):
    # Setup seed data
    persona = PersonaProfile(id="p_res1", name="Tester", domain="Testing")
    agent = Agent(id="a_res1", persona_id="p_res1")
    thread = ResearchThread(id="t_res1", agent_id="a_res1", title="Thread 1", description="Desc")
    question = ResearchQuestion(id="q_res1", thread_id="t_res1", question="What is the answer?")
    
    db_session.add_all([persona, agent, thread, question])
    await db_session.commit()
    
    llm = FakeLLMProvider()
    search = FakeSearchProvider()
    service = ResearchService(db_session, llm, search)
    service.fetcher = mock_fetcher # Monkeypatch fetcher
    
    run_id = await service.research_question("q_res1")
    assert run_id is not None
    
    # Verify DB state
    run = await db_session.execute(select(ResearchRun).where(ResearchRun.id == run_id))
    run = run.scalar_one()
    
    assert run.status == "COMPLETED"
    assert len(run.queries_generated) == 2
    # Fake search provider returns 2 results per query. 2 queries * 2 results = 4.
    # But wait, fake search results might be identical for both queries?
    # FakeSearchProvider uses hash(query), so they will be different URLs.
    # FakeSearchProvider returns 1 result per search, 2 queries = 2 results.
    assert len(run.sources_discovered) == 2
    assert len(run.sources_processed) == 2
    
    # Check sources and evidence are populated
    sources = await db_session.execute(select(Source))
    sources = sources.scalars().all()
    assert len(sources) == 2
    
    evidence = await db_session.execute(select(Evidence))
    evidence = evidence.scalars().all()
    assert len(evidence) == 2
    
    for ev in evidence:
        assert ev.evidence_text == "Grounded Claim Test Content"
        assert ev.polarity == "SUPPORTS"

@pytest.mark.asyncio
async def test_research_service_partial_run(db_session):
    # Test partial run when fetch fails for some urls
    persona = PersonaProfile(id="p_res2", name="Tester2", domain="Testing")
    agent = Agent(id="a_res2", persona_id="p_res2")
    thread = ResearchThread(id="t_res2", agent_id="a_res2", title="Thread 2", description="Desc")
    question = ResearchQuestion(id="q_res2", thread_id="t_res2", question="What is the answer?")
    
    db_session.add_all([persona, agent, thread, question])
    await db_session.commit()
    
    llm = FakeLLMProvider()
    
    class MixedSearchProvider:
        async def search(self, query: str, limit: int = 5):
            from app.schemas.research import SearchResult
            return [
                SearchResult(url="https://example.com/good", title="Good"),
                SearchResult(url="https://example.com/fail", title="Fail") # 'fail' triggers MockFetcher exception
            ]
            
    search = MixedSearchProvider()
    service = ResearchService(db_session, llm, search)
    service.fetcher = MockFetcher() # Monkeypatch
    
    run_id = await service.research_question("q_res2")
    
    run = await db_session.execute(select(ResearchRun).where(ResearchRun.id == run_id))
    run = run.scalar_one()
    
    assert run.status == "PARTIAL"
    assert len(run.sources_processed) < len(run.sources_discovered)
    assert len(run.sources_processed) > 0
