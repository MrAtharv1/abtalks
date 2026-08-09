"""
Lifecycle tests for THREAD agent initialization and runtime.

Critical contract:
    POST /api/agent/init
        → agent.status == ACTIVE in DB
        → runtime_manager.start() called
        → autonomous runtime loop running
        → GET /api/agent/feed must work WITHOUT ever calling /start
"""
import pytest
import asyncio
from httpx import AsyncClient
from sqlalchemy.future import select

from app.db.models import Agent
from app.runtime.agent_runtime import runtime_manager


# ---------------------------------------------------------------------------
# Test 1 — Initialization auto-starts runtime (CRITICAL evaluator contract)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_init_auto_starts_runtime(client: AsyncClient, setup_db):
    """
    /api/agent/init must start the runtime WITHOUT any /start call.
    This is the evaluator contract: init once, then only poll /feed.
    """
    init_res = await client.post(
        "/api/agent/init",
        json={"persona": {"name": "Eva", "domain": "AI Safety"}}
    )
    assert init_res.status_code == 200, init_res.text
    agent_id = init_res.json()["agentId"]
    assert agent_id

    assert agent_id in runtime_manager.active_tasks, (
        "Runtime task was not created by init. "
        "Evaluator will never call /start — this is the critical violation."
    )
    assert not runtime_manager.active_tasks[agent_id].done()

    await runtime_manager.stop_and_wait(agent_id)


# ---------------------------------------------------------------------------
# Test 2 — Status persisted as ACTIVE before runtime starts
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_init_persists_active_status(client: AsyncClient, setup_db, db_session):
    """
    agent.status must be committed as ACTIVE before runtime_manager.start().
    Server restart recovery depends on this.
    """
    init_res = await client.post(
        "/api/agent/init",
        json={"persona": {"name": "Leo", "domain": "ML Engineering"}}
    )
    assert init_res.status_code == 200
    agent_id = init_res.json()["agentId"]

    result = await db_session.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    assert agent is not None
    assert agent.status == "ACTIVE", (
        f"Expected status='ACTIVE' but got '{agent.status}'. "
        "Status must be committed ACTIVE so server-restart recovery works."
    )

    await runtime_manager.stop_and_wait(agent_id)


# ---------------------------------------------------------------------------
# Test 3 — No duplicate runtime (idempotency)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_duplicate_runtime(client: AsyncClient, setup_db):
    """
    init then /start then /start must result in exactly ONE runtime task.
    RuntimeManager.start() is idempotent by design.
    """
    init_res = await client.post(
        "/api/agent/init",
        json={"persona": {"name": "Max", "domain": "Robotics"}}
    )
    assert init_res.status_code == 200
    agent_id = init_res.json()["agentId"]

    original_task = runtime_manager.active_tasks.get(agent_id)
    assert original_task is not None

    start_res = await client.post(f"/api/agent/{agent_id}/start")
    assert start_res.status_code == 200
    assert start_res.json()["status"] == "already_running"
    assert runtime_manager.active_tasks.get(agent_id) is original_task

    started = runtime_manager.start(agent_id)
    assert started is False
    assert runtime_manager.active_tasks.get(agent_id) is original_task

    await runtime_manager.stop_and_wait(agent_id)


# ---------------------------------------------------------------------------
# Test 4 — Feed works without /start (evaluator flow)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_feed_works_without_start(client: AsyncClient, setup_db):
    """
    The evaluator flow: POST /init then only GET /feed. /start is never called.
    """
    init_res = await client.post(
        "/api/agent/init",
        json={"persona": {"name": "Kai", "domain": "AI Ethics"}}
    )
    assert init_res.status_code == 200
    agent_id = init_res.json()["agentId"]

    feed_res = await client.get(f"/api/agent/feed?agentId={agent_id}")
    assert feed_res.status_code == 200
    body = feed_res.json()
    assert "posts" in body
    assert isinstance(body["posts"], list)

    await runtime_manager.stop_and_wait(agent_id)


# ---------------------------------------------------------------------------
# Test 5 — Start / Stop lifecycle still works after init auto-start
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manual_stop_start_after_init(client: AsyncClient, setup_db):
    """
    After init auto-starts the runtime, manual Stop/Start controls must work.
    """
    init_res = await client.post(
        "/api/agent/init",
        json={"persona": {"name": "Noa", "domain": "Open Source AI"}}
    )
    assert init_res.status_code == 200
    agent_id = init_res.json()["agentId"]
    assert agent_id in runtime_manager.active_tasks

    stop_res = await client.post(f"/api/agent/{agent_id}/stop")
    assert stop_res.status_code == 200
    assert stop_res.json()["status"] == "stopped"
    await asyncio.sleep(0.1)
    assert agent_id not in runtime_manager.active_tasks

    start_res = await client.post(f"/api/agent/{agent_id}/start")
    assert start_res.status_code == 200
    assert start_res.json()["status"] == "started"
    assert agent_id in runtime_manager.active_tasks
    assert not runtime_manager.active_tasks[agent_id].done()

    await client.post(f"/api/agent/{agent_id}/stop")
    stop2 = await client.post(f"/api/agent/{agent_id}/stop")
    assert stop2.status_code == 200


# ---------------------------------------------------------------------------
# Test 6 — Server-restart recovery (recover_active_agents) — unit-level
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_startup_recovery_still_works(setup_db):
    """
    recover_active_agents() must call start() for every agent row returned
    by the DB query where status='ACTIVE'.

    This is tested as a unit test: we mock the DB query to return a fake ACTIVE
    agent, then verify runtime_manager.start() was invoked for that agent.
    The production integration (real DB → real restart) is covered by the
    ACTIVE status commitment verified in test_init_persists_active_status.
    """
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.runtime.agent_runtime import RuntimeManager

    fake_agent_id = "recovery-test-agent-id"

    # Build a fake agent ORM object
    fake_agent = MagicMock()
    fake_agent.id = fake_agent_id

    # Patch AsyncSessionLocal inside agent_runtime so it returns our fake agent
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fake_agent]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_session_local = MagicMock(return_value=mock_session)

    fresh_manager = RuntimeManager()

    with patch("app.runtime.agent_runtime.AsyncSessionLocal", mock_session_local):
        # Also patch start() itself to avoid spawning real tasks in this unit test
        started_ids = []
        original_start = fresh_manager.start

        def capturing_start(agent_id: str) -> bool:
            started_ids.append(agent_id)
            return True

        fresh_manager.start = capturing_start
        await fresh_manager.recover_active_agents()

    assert fake_agent_id in started_ids, (
        f"recover_active_agents() did not call start() for ACTIVE agent '{fake_agent_id}'. "
        "Server-restart recovery is broken."
    )
