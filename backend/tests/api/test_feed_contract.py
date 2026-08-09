import pytest
from httpx import AsyncClient
import uuid

@pytest.mark.asyncio
async def test_feed_contract(client: AsyncClient, db_session):
    # 1. Initialize
    init_payload = {
        "persona": {
            "name": "TestAda",
            "domain": "AI Testing"
        }
    }
    response = await client.post("/api/agent/init", json=init_payload)
    assert response.status_code == 200
    data = response.json()
    assert "agentId" in data
    agent_id = data["agentId"]

    # 2. Test Feed Contract
    feed_url = f"/api/agent/feed?agentId={agent_id}"
    
    # Empty feed
    feed_res = await client.get(feed_url)
    assert feed_res.status_code == 200
    feed_data = feed_res.json()
    assert "posts" in feed_data
    assert isinstance(feed_data["posts"], list)
    
    # 3. Simulate inserting a post directly in DB
    from app.db.models import Post
    import json
    from datetime import datetime, timedelta
    import asyncio
    
    now = datetime.utcnow()
    
    p1 = Post(
        id=str(uuid.uuid4()),
        agent_id=agent_id,
        text="First test post.",
        rationale=json.dumps({"why": "test"}),
        sources=["http://test.com/1"],
        created_at=now - timedelta(seconds=10)
    )
    db_session.add(p1)
    await db_session.commit()
        
    # 4. Check feed again
    feed_res = await client.get(feed_url)
    feed_data = feed_res.json()
    assert len(feed_data["posts"]) == 1
    post1 = feed_data["posts"][0]
    assert post1["text"] == "First test post."
    assert "rationale" in post1
    assert "sources" in post1
    assert post1["sources"] == ["http://test.com/1"]
    
    # 5. Insert newer post
    p2 = Post(
        id=str(uuid.uuid4()),
        agent_id=agent_id,
        text="Second test post.",
        rationale=json.dumps({"why": "test 2"}),
        sources=[],
        created_at=now
    )
    db_session.add(p2)
    await db_session.commit()
        
    # 6. Check feed ordering (newest first)
    feed_res = await client.get(feed_url)
    feed_data = feed_res.json()
    assert len(feed_data["posts"]) == 2
    assert feed_data["posts"][0]["text"] == "Second test post."
    assert feed_data["posts"][1]["text"] == "First test post."
