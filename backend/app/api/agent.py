from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.schemas.agent import AgentInitRequest, AgentInitResponse
from app.schemas.feed import FeedResponse
from app.db.models import Agent
from app.services import agent_service
from app.core.logging import setup_logging
from app.llm.base import LLMProvider
from app.llm.provider import get_llm_provider
from app.services.persona_service import PersonaService
from app.runtime.agent_runtime import runtime_manager

logger = setup_logging()
router = APIRouter(prefix="/api/agent", tags=["agent"])


def get_persona_service(llm_provider: LLMProvider = Depends(get_llm_provider)) -> PersonaService:
    return PersonaService(llm_provider=llm_provider)


@router.post("/init", response_model=AgentInitResponse)
async def init_agent(
    request: AgentInitRequest,
    db: AsyncSession = Depends(get_db),
    persona_service: PersonaService = Depends(get_persona_service)
):
    try:
        agent_id = await agent_service.initialize_agent(db, request, persona_service)
        return AgentInitResponse(agentId=agent_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during initialization: {e}")
        raise HTTPException(status_code=500, detail="Initialization failed")


@router.get("/feed", response_model=FeedResponse)
async def get_feed(agentId: str, db: AsyncSession = Depends(get_db)):
    return await agent_service.get_agent_feed(db, agentId)


@router.post("/{agent_id}/start")
async def start_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
        
    logger.info(f"[API] agent_start_requested agent_id={agent_id}")
    
    started = runtime_manager.start(agent_id)
    if not started:
        return {"status": "already_running"}
        
    agent.status = "ACTIVE"
    await db.commit()
    
    return {"status": "started"}


@router.post("/{agent_id}/stop")
async def stop_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
        
    logger.info(f"[API] agent_stop_requested agent_id={agent_id}")
    if agent_id in runtime_manager.active_tasks:
        await runtime_manager.stop_and_wait(agent_id)
        
    # Refresh agent from db after runtime wait
    agent = await db.get(Agent, agent_id)
    if agent:
        agent.status = "STOPPED"
        await db.commit()
        
    return {"status": "stopped"}


@router.get("/status")
async def get_agent_status(agentId: str, db: AsyncSession = Depends(get_db)):
    """
    Runtime observability dashboard for a specific agent.
    Returns state machine, budget, cadence, and cycle statistics.
    This endpoint is read-only and does not trigger any generation.
    """
    # Verify agent exists in DB
    status = runtime_manager.get_agent_status(agentId)
    db_state = await agent_service.get_debug_state(db, agentId)
    return {**status, **db_state}


@router.get("/debug/agent/{agent_id}/state")
async def get_agent_state(agent_id: str, db: AsyncSession = Depends(get_db)):
    return await agent_service.get_debug_state(db, agent_id)

@router.get("/{agent_id}/workspace")
async def get_agent_workspace_endpoint(agent_id: str, db: AsyncSession = Depends(get_db)):
    return await agent_service.get_agent_workspace(db, agent_id)
