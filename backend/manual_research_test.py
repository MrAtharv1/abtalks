import asyncio
import json
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.database import AsyncSessionLocal, engine, Base
from sqlalchemy.future import select
from app.llm.provider import get_llm_provider, FakeLLMProvider
from app.research.search import FakeSearchProvider
from app.research.service import ResearchService
from app.db.models import Agent, PersonaProfile, ResearchThread, ResearchQuestion, ResearchRun, Source, Evidence

app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()

async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

async def run_manual_test():
    await setup_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        print("\n--- 1. INITIALIZING ADA ---")
        res = await client.post("/api/agent/init", json={"persona": {"name": "Ada", "domain": "AI Security"}})
        agent_id = res.json().get("agentId")
        print(f"Created Agent ID: {agent_id}")
        
    async with AsyncSessionLocal() as db:
        agent = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = agent.scalar_one()
        
        question_req = await db.execute(select(ResearchQuestion).where(ResearchQuestion.thread.has(agent_id=agent_id)).limit(1))
        question = question_req.scalar_one()
        print(f"\n--- 2. SELECTED QUESTION: {question.question} ({question.id}) ---")
        
        print("\n--- 3. RUNNING RESEARCH (RUN 1) ---")
        llm = FakeLLMProvider()
        
        class TestMixedSearchProvider:
            async def search(self, query: str, limit: int = 5):
                from app.schemas.research import SearchResult
                return [
                    SearchResult(url="https://example.com/good", title="Good Source", source_domain="example.com"),
                    SearchResult(url="https://example.com/fail", title="Bad Source", source_domain="example.com") # Will fail to fetch
                ]
                
        search = TestMixedSearchProvider()
        service = ResearchService(db, llm, search)
        
        # Monkeypatch fetcher to fail on 'fail' URL
        from app.schemas.research import FetchedDocument
        class ManualMockFetcher:
            async def fetch(self, url: str) -> FetchedDocument:
                if "fail" in url:
                    raise ValueError("Simulated HTTP failure for manual test")
                return FetchedDocument(
                    url=url, final_url=url, content_type="text/html",
                    raw_content=b"<html><body><p>Grounded Claim Test Content for AI Security.</p></body></html>",
                    title="Good Source Title"
                )
        service.fetcher = ManualMockFetcher()
        
        run_id_1 = await service.research_question(question.id)
        
        print("\n--- 4. RUNNING RESEARCH (RUN 2) ---")
        # Run again to test deduplication
        run_id_2 = await service.research_question(question.id)
        
        print("\n--- 5. INSPECTING RESULTS ---")
        run1 = await db.execute(select(ResearchRun).where(ResearchRun.id == run_id_1))
        run1 = run1.scalar_one()
        print(f"Run 1 Status: {run1.status}")
        print(f"Run 1 Sources Discovered: {run1.sources_discovered}")
        print(f"Run 1 Sources Processed: {run1.sources_processed}")
        
        sources = await db.execute(select(Source))
        sources = sources.scalars().all()
        print(f"\nTotal Unique Sources in DB: {len(sources)}")
        for s in sources:
            print(f" - {s.url} (Hash: {s.content_hash})")
            
        evidence = await db.execute(select(Evidence))
        evidence = evidence.scalars().all()
        print(f"\nTotal Evidence Extracted: {len(evidence)}")
        for e in evidence:
            print(f" - Claim: {e.claim} | Polarity: {e.polarity} | Grounded Text: {e.evidence_text}")
            
    print("\n--- 6. CHECKING FEED ---")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        feed = await client.get(f"/api/agent/feed?agentId={agent_id}")
        print(json.dumps(feed.json(), indent=2))

if __name__ == "__main__":
    asyncio.run(run_manual_test())
