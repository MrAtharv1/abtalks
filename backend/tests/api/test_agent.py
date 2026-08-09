import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.db.models import Agent, Post, PersonaProfile, ResearchThread, ResearchQuestion
from app.llm.provider import get_llm_provider
from app.llm.base import LLMProvider
import uuid
from typing import Type, TypeVar
from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)

@pytest.mark.asyncio
async def test_init_agent_success(client: AsyncClient, setup_db):
    response = await client.post(
        "/api/agent/init",
        json={"persona": {"name": "Ada", "domain": "AI Security"}}
    )
    assert response.status_code == 200
    data = response.json()
    assert "agentId" in data
    
    agent_id = data["agentId"]
    
    # Verify DB state directly
    from tests.conftest import TestingSessionLocal
    async with TestingSessionLocal() as db:
        agent = await db.execute(
            select(Agent)
            .options(selectinload(Agent.persona), selectinload(Agent.research_threads).selectinload(ResearchThread.questions))
            .where(Agent.id == agent_id)
        )
        agent = agent.scalar_one_or_none()
        
        assert agent is not None
        assert agent.persona is not None
        assert agent.persona.name == "Ada"
        assert agent.persona.domain == "AI Security"
        assert agent.persona.voice_style == "Analytical and concise"
        
        # Verify research threads
        assert len(agent.research_threads) == 3
        assert agent.research_threads[0].title == "Thread 1"
        assert len(agent.research_threads[0].questions) == 2

@pytest.mark.asyncio
async def test_init_agent_invalid(client: AsyncClient):
    response = await client.post(
        "/api/agent/init",
        json={"persona": {"name": "Ada"}} # Missing domain
    )
    assert response.status_code == 422 # Validation error

@pytest.mark.asyncio
async def test_feed_valid_agent(client: AsyncClient):
    init_response = await client.post(
        "/api/agent/init",
        json={"persona": {"name": "Ada", "domain": "AI Security"}}
    )
    agent_id = init_response.json()["agentId"]
    
    response = await client.get(f"/api/agent/feed?agentId={agent_id}")
    assert response.status_code == 200
    data = response.json()
    assert "posts" in data
    assert len(data["posts"]) == 0

@pytest.mark.asyncio
async def test_feed_unknown_agent(client: AsyncClient):
    fake_id = str(uuid.uuid4())
    response = await client.get(f"/api/agent/feed?agentId={fake_id}")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_feed_post_ordering(client: AsyncClient, setup_db):
    from tests.conftest import TestingSessionLocal
    from datetime import datetime, timedelta
    
    agent_id = str(uuid.uuid4())
    persona_id = str(uuid.uuid4())
    
    async with TestingSessionLocal() as db:
        persona = PersonaProfile(id=persona_id, name="Ada", domain="Sec")
        agent = Agent(id=agent_id, status="ACTIVE", persona_id=persona_id)
        
        db.add(persona)
        db.add(agent)
        
        now = datetime.utcnow()
        post1 = Post(id=str(uuid.uuid4()), agent_id=agent_id, text="First", created_at=now - timedelta(days=2))
        post2 = Post(id=str(uuid.uuid4()), agent_id=agent_id, text="Second", created_at=now - timedelta(days=1))
        post3 = Post(id=str(uuid.uuid4()), agent_id=agent_id, text="Third", created_at=now)
        
        db.add_all([post1, post2, post3])
        await db.commit()
        
    response = await client.get(f"/api/agent/feed?agentId={agent_id}")
    assert response.status_code == 200
    posts = response.json()["posts"]
    assert len(posts) == 3
    assert posts[0]["text"] == "Third"
    assert posts[1]["text"] == "Second"
    assert posts[2]["text"] == "First"

@pytest.mark.asyncio
async def test_init_agent_llm_failure(client: AsyncClient, setup_db, monkeypatch):
    # Mock the LLM provider to throw an exception
    class FailingLLMProvider(LLMProvider):
        async def generate_structured(self, prompt: str, schema: Type[T]) -> T:
            raise ValueError("Simulated LLM API failure")
            
    from app.main import app
    app.dependency_overrides[get_llm_provider] = lambda: FailingLLMProvider()
    
    response = await client.post(
        "/api/agent/init",
        json={"persona": {"name": "FailBot", "domain": "Failure"}}
    )
    
    assert response.status_code == 500
    
    # Restore the fake provider for other tests
    from tests.conftest import override_get_llm_provider
    app.dependency_overrides[get_llm_provider] = override_get_llm_provider
    
    # Verify rollback - no agent or persona was created
    from tests.conftest import TestingSessionLocal
    async with TestingSessionLocal() as db:
        agents = await db.execute(select(Agent))
        personas = await db.execute(select(PersonaProfile))
        
        assert len(agents.scalars().all()) == 0
        assert len(personas.scalars().all()) == 0

@pytest.mark.asyncio
async def test_init_multiple_agents(client: AsyncClient, setup_db):
    res1 = await client.post("/api/agent/init", json={"persona": {"name": "Ada", "domain": "AI Security"}})
    res2 = await client.post("/api/agent/init", json={"persona": {"name": "Maya", "domain": "Robotics"}})
    
    assert res1.status_code == 200
    assert res2.status_code == 200
    
    agent1_id = res1.json()["agentId"]
    agent2_id = res2.json()["agentId"]
    
    assert agent1_id != agent2_id
    
    from tests.conftest import TestingSessionLocal
    async with TestingSessionLocal() as db:
        agents = await db.execute(
            select(Agent).options(selectinload(Agent.persona)).where(Agent.id.in_([agent1_id, agent2_id]))
        )
        agents_list = agents.scalars().all()
        assert len(agents_list) == 2
        
        # Verify independence
        names = set([a.persona.name for a in agents_list])
        assert names == {"Ada", "Maya"}
