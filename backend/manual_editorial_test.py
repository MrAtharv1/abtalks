import asyncio
import uuid
import os
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.db.database import engine, Base, AsyncSessionLocal
from app.db.models import Agent, PersonaProfile, ResearchThread, ResearchQuestion, Evidence, Belief, BeliefRevision, Post, Source
from app.editorial.service import EditorialService
from app.llm.provider import FakeLLMProvider

async def run():
    # 1. Init
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async with AsyncSessionLocal() as db:
        print("\n--- 1. INITIALIZING ADA ---")
        agent_id = str(uuid.uuid4())
        persona = PersonaProfile(id=str(uuid.uuid4()), name="Ada", domain="AI Security", voice_style="Analytical")
        agent = Agent(id=agent_id, persona_id=persona.id)
        
        thread = ResearchThread(id=str(uuid.uuid4()), agent_id=agent_id, title="Prompt Injection Defenses", description="Evaluating tool-using AI agents")
        question = ResearchQuestion(id=str(uuid.uuid4()), thread_id=thread.id, question="How effective are current defenses against indirect prompt injection in tool-using AI agents?")
        db.add_all([persona, agent, thread, question])
        await db.commit()
        
        print("\n--- 2. CREATING INITIAL EVIDENCE ---")
        src = Source(id=str(uuid.uuid4()), url="https://example.com/defense", canonical_url="https://example.com/defense")
        ev = Evidence(id=str(uuid.uuid4()), question_id=question.id, source_id=src.id, claim="Defenses work", evidence_text="Current defenses provide meaningful protection.", polarity="SUPPORTS", confidence=0.8, relevance_score=0.9, source_quality_score=0.9)
        db.add_all([src, ev])
        await db.commit()
        
        print("\n--- 3. SYNTHESIZING BELIEF ---")
        belief = Belief(id=str(uuid.uuid4()), agent_id=agent_id, thread_id=thread.id, statement="Current defenses provide meaningful but incomplete protection.", confidence=0.72, importance=0.8, status="ACTIVE")
        rev = BeliefRevision(id=str(uuid.uuid4()), belief_id=belief.id, previous_confidence=0.0, new_confidence=0.72, change_type="INITIAL", reason="Initial synthesis", trigger_evidence_id=ev.id)
        db.add_all([belief, rev])
        await db.commit()
        
        print("\n--- 4. GENERATING EDITORIAL CANDIDATE (POST 1) ---")
        llm = FakeLLMProvider()
        editorial_svc = EditorialService(db, llm)
        editorial_svc.selector_service.threshold = 0.1
        
        post1 = await editorial_svc.generate_next_editorial_item(agent_id)
        if post1:
            print(f"POST 1: {post1.text}")
            print(f"Rationale: {json.loads(post1.rationale)['why_selected']}")
            
        print("\n--- 5. NEW CONTRADICTORY EVIDENCE ARRIVES ---")
        src2 = Source(id=str(uuid.uuid4()), url="https://example.com/bypass", canonical_url="https://example.com/bypass")
        ev2 = Evidence(id=str(uuid.uuid4()), question_id=question.id, source_id=src2.id, claim="Defenses fail", evidence_text="contradict: New benchmark shows 100% bypass.", polarity="CONTRADICTS", confidence=0.9, relevance_score=1.0, source_quality_score=1.0)
        db.add_all([src2, ev2])
        await db.commit()
        
        print("\n--- 6. BELIEF REVISION ---")
        belief.confidence = 0.41
        belief.status = "DISPUTED"
        rev2 = BeliefRevision(id=str(uuid.uuid4()), belief_id=belief.id, previous_confidence=0.72, new_confidence=0.41, change_type="DISPUTED", reason="New benchmark shows bypass.", trigger_evidence_id=ev2.id)
        db.add(rev2)
        await db.commit()
        
        print("\n--- 7. GENERATING EDITORIAL CANDIDATE (POST 2) ---")
        post2 = await editorial_svc.generate_next_editorial_item(agent_id)
        if post2:
            print(f"POST 2: {post2.text}")
            print(f"Rationale: {json.loads(post2.rationale)['why_selected']}")
            
        print("\n--- 8. FEED RESULTS ---")
        # Simulate GET /api/agent/feed
        posts = await db.execute(select(Post).where(Post.agent_id == agent_id).order_by(Post.created_at.desc()))
        for p in posts.scalars().all():
            print(f"[{p.created_at}] Post ID: {p.id}")
            print(f"Text: {p.text}")
            print(f"Sources: {p.sources}")
            print("-" * 20)

if __name__ == "__main__":
    asyncio.run(run())
