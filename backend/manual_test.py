import asyncio
from httpx import AsyncClient
from app.main import app
from app.llm.provider import get_llm_provider, FakeLLMProvider
import json

app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()

from app.db.database import engine, Base

async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def run_manual_test():
    await setup_db()
    async with AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        print("--- INITIALIZING ADA ---")
        res1 = await client.post("/api/agent/init", json={"persona": {"name": "Ada", "domain": "AI Security"}})
        print(f"Status: {res1.status_code}")
        data1 = res1.json()
        print(json.dumps(data1, indent=2))
        
        agent_id_1 = data1.get("agentId")
        if agent_id_1:
            print(f"\n--- FETCHING FEED FOR ADA ({agent_id_1}) ---")
            feed1 = await client.get(f"/api/agent/feed?agentId={agent_id_1}")
            print(json.dumps(feed1.json(), indent=2))

        print("\n--- INITIALIZING MAYA ---")
        res2 = await client.post("/api/agent/init", json={"persona": {"name": "Maya", "domain": "Robotics"}})
        data2 = res2.json()
        print(json.dumps(data2, indent=2))
        
        agent_id_2 = data2.get("agentId")
        if agent_id_2:
            print(f"\n--- FETCHING FEED FOR MAYA ({agent_id_2}) ---")
            feed2 = await client.get(f"/api/agent/feed?agentId={agent_id_2}")
            print(json.dumps(feed2.json(), indent=2))

        print("\n--- DIRECT DB INSPECTION FOR ADA ---")
        from app.db.database import AsyncSessionLocal
        from sqlalchemy.future import select
        from sqlalchemy.orm import selectinload
        from app.db.models import Agent, ResearchThread
        async with AsyncSessionLocal() as db:
            agent = await db.execute(
                select(Agent)
                .options(selectinload(Agent.persona), selectinload(Agent.research_threads).selectinload(ResearchThread.questions))
                .where(Agent.id == agent_id_1)
            )
            agent = agent.scalar_one_or_none()
            if agent:
                print(f"Persona Name: {agent.persona.name}")
                print(f"Voice Style: {agent.persona.voice_style}")
                print(f"Threads Count: {len(agent.research_threads)}")
                if len(agent.research_threads) > 0:
                    print(f"First Thread: {agent.research_threads[0].title}")
                    print(f"Questions in First Thread: {len(agent.research_threads[0].questions)}")

if __name__ == "__main__":
    import httpx
    asyncio.run(run_manual_test())
