import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from app.db.models import Agent, PersonaProfile, Post, ResearchThread, ResearchQuestion, Source, Evidence
from app.schemas.agent import AgentInitRequest
from app.schemas.feed import FeedResponse, PostResponse
from app.services.persona_service import PersonaService
from fastapi import HTTPException
import logging

logger = logging.getLogger("thread")

# Imported lazily inside initialize_agent to avoid circular imports at module load
def _get_runtime_manager():
    from app.runtime.agent_runtime import runtime_manager
    return runtime_manager

async def initialize_agent(db: AsyncSession, request: AgentInitRequest, persona_service: PersonaService) -> str:
    logger.info("initialization_started")
    agent_id = str(uuid.uuid4())
    persona_id = str(uuid.uuid4())
    
    # Generate persona using LLM before modifying the database
    # This might raise an exception which will bubble up and be caught by the router
    generated_persona = await persona_service.initialize_persona(
        name=request.persona.name,
        domain=request.persona.domain
    )

    # If successful, begin transactional persist
    try:
        new_persona = PersonaProfile(
            id=persona_id,
            name=request.persona.name,
            domain=request.persona.domain,
            voice_style=generated_persona.voice_style,
            technicality=generated_persona.technicality,
            skepticism=generated_persona.skepticism,
            formality=generated_persona.formality,
            preferred_content_types=generated_persona.preferred_content_types,
            avoided_content_types=generated_persona.avoided_content_types,
            editorial_principles=generated_persona.editorial_principles,
            evidence_preferences=generated_persona.evidence_preferences
        )
        db.add(new_persona)
        
        new_agent = Agent(
            id=agent_id,
            status="ACTIVE",   # ACTIVE from birth — runtime starts after commit
            persona_id=persona_id
        )
        db.add(new_agent)

        for thread_data in generated_persona.research_threads:
            thread_id = str(uuid.uuid4())
            new_thread = ResearchThread(
                id=thread_id,
                agent_id=agent_id,
                title=thread_data.title,
                description=thread_data.description,
                priority=thread_data.priority,
                status="ACTIVE"
            )
            db.add(new_thread)
            
            for q_data in thread_data.questions:
                new_q = ResearchQuestion(
                    id=str(uuid.uuid4()),
                    thread_id=thread_id,
                    question=q_data.question,
                    importance=q_data.importance,
                    confidence=q_data.confidence,
                    status="OPEN"
                )
                db.add(new_q)

        logger.info("initialization_persisted")
        await db.commit()
        logger.info("initialization_completed")

        # Start the autonomous runtime AFTER the commit succeeds.
        # Uses RuntimeManager.start() which is idempotent — calling it again
        # for the same agent_id is a safe no-op (returns False, logs warning).
        _get_runtime_manager().start(agent_id)
        logger.info(f"initialization_runtime_started agent_id={agent_id}")

        return agent_id
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to persist initialization transaction: {e}")
        raise HTTPException(status_code=500, detail="Internal initialization error")

async def get_agent_feed(db: AsyncSession, agent_id: str) -> FeedResponse:
    from app.db.models import EditorialCandidate
    
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
        
    posts_result = await db.execute(
        select(Post)
        .where(Post.agent_id == agent_id)
        .order_by(desc(Post.created_at))
        .limit(50)
    )
    posts = posts_result.scalars().all()
    
    candidates_result = await db.execute(
        select(EditorialCandidate)
        .where(EditorialCandidate.agent_id == agent_id)
        .where(EditorialCandidate.status.in_(["PENDING", "SELECTED", "FAILED"]))
        .order_by(desc(EditorialCandidate.created_at))
        .limit(20)
    )
    candidates = candidates_result.scalars().all()
    
    feed_items = []
    
    for post in posts:
        feed_items.append(
            PostResponse(
                id=post.id, 
                createdAt=post.created_at,
                text=post.text,
                rationale=post.rationale,
                sources=post.sources or [],
                status="PUBLISHED",
                is_candidate=False
            )
        )
        
    for cand in candidates:
        # Generate a placeholder text from headline and summary for the candidate
        cand_text = f"**{cand.headline}**\n\n{cand.summary}"
        feed_items.append(
            PostResponse(
                id=cand.id,
                createdAt=cand.created_at,
                text=cand_text,
                rationale=f"Candidate generated with {cand.editorial_significance:.2f} significance.",
                sources=[],
                status=cand.status,
                is_candidate=True
            )
        )
        
    # Sort the combined items by createdAt descending
    feed_items.sort(key=lambda x: x.createdAt, reverse=True)
    
    return FeedResponse(posts=feed_items)

async def get_debug_state(db: AsyncSession, agent_id: str) -> dict:
    from app.db.models import Belief, Post, AgentCycle, Evidence
    from sqlalchemy import func
    
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
        
    beliefs_count = await db.execute(select(func.count(Belief.id)).where(Belief.agent_id == agent_id))
    posts_count = await db.execute(select(func.count(Post.id)).where(Post.agent_id == agent_id))
    cycles_count = await db.execute(select(func.count(AgentCycle.id)).where(AgentCycle.agent_id == agent_id))
    
    return {
        "status": agent.status,
        "runtime_status": agent.runtime_status,
        "beliefs_count": beliefs_count.scalar() or 0,
        "posts_count": posts_count.scalar() or 0,
        "cycles_count": cycles_count.scalar() or 0
    }
from app.schemas.agent import WorkspaceResponse, ThreadResponse, QuestionResponse, SourceResponse, EvidenceResponse, BeliefResponse

async def get_agent_workspace(db: AsyncSession, agent_id: str) -> WorkspaceResponse:
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(Agent)
        .options(
            selectinload(Agent.persona),
            selectinload(Agent.research_threads).selectinload(ResearchThread.questions).selectinload(ResearchQuestion.evidence).selectinload(Evidence.source),
            selectinload(Agent.research_threads).selectinload(ResearchThread.beliefs),
        )
        .where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
        
    # Get recent sources directly to limit count
    sources_res = await db.execute(select(Source).order_by(desc(Source.retrieved_at)).limit(50))
    sources = sources_res.scalars().all()
    
    threads_resp = []
    for thread in agent.research_threads:
        questions_resp = []
        for q in thread.questions:
            evidence_resp = []
            for ev in q.evidence:
                evidence_resp.append(EvidenceResponse(
                    id=ev.id, claim=ev.claim, evidence_text=ev.evidence_text,
                    relevance_score=ev.relevance_score, source_quality_score=ev.source_quality_score,
                    confidence=ev.confidence, polarity=ev.polarity, source_url=ev.source.url if ev.source else None
                ))
            questions_resp.append(QuestionResponse(
                id=q.id, question=q.question, status=q.status,
                importance=q.importance, confidence=q.confidence, evidence=evidence_resp
            ))
            
        beliefs_resp = []
        for b in thread.beliefs:
            beliefs_resp.append(BeliefResponse(
                id=b.id, statement=b.statement, confidence=b.confidence,
                importance=b.importance, status=b.status
            ))
            
        threads_resp.append(ThreadResponse(
            id=thread.id, title=thread.title, description=thread.description,
            status=thread.status, priority=thread.priority,
            questions=questions_resp, beliefs=beliefs_resp
        ))
        
    sources_resp = [
        SourceResponse(id=s.id, url=s.url, title=s.title, domain=s.domain, retrieved_at=s.retrieved_at)
        for s in sources
    ]
    
    return WorkspaceResponse(
        agent_id=agent.id,
        status=agent.status,
        persona={"name": agent.persona.name, "domain": agent.persona.domain},
        threads=threads_resp,
        sources=sources_resp
    )
