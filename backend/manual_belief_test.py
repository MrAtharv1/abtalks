import asyncio
import uuid
from app.db.database import AsyncSessionLocal, engine, Base
from sqlalchemy.future import select
from app.llm.provider import FakeLLMProvider
from app.memory.belief_engine import BeliefService
from app.memory.service import MemoryService
from app.db.models import Agent, PersonaProfile, ResearchThread, ResearchQuestion, Source, Evidence

async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

async def run_manual_test():
    await setup_db()
    async with AsyncSessionLocal() as db:
        print("\n--- 1. INITIALIZING ADA ---")
        p = PersonaProfile(id="p_ada", name="Ada", domain="AI Security")
        a = Agent(id="a_ada", persona_id="p_ada")
        t = ResearchThread(id="t_ada", agent_id="a_ada", title="Prompt Injection", description="")
        q = ResearchQuestion(id="q_ada", thread_id="t_ada", question="How effective are current defenses against indirect prompt injection in tool-using AI agents?")
        
        s_good = Source(id="s_good", url="http://good", canonical_url="http://good", quality_score=1.0)
        s_med = Source(id="s_med", url="http://med", canonical_url="http://med", quality_score=0.6)
        
        db.add_all([p, a, t, q, s_good, s_med])
        
        print("\n--- 2. CREATING INITIAL EVIDENCE ---")
        e_a = Evidence(id="e_a", question_id="q_ada", source_id="s_good", claim="Defenses work.", evidence_text="Tests show high mitigation.", relevance_score=1.0, source_quality_score=1.0, confidence=0.9, polarity="SUPPORTS")
        e_b = Evidence(id="e_b", question_id="q_ada", source_id="s_good", claim="Firewalls catch prompts.", evidence_text="LLM firewalls block attacks.", relevance_score=1.0, source_quality_score=1.0, confidence=0.9, polarity="SUPPORTS")
        e_c = Evidence(id="e_c", question_id="q_ada", source_id="s_med", claim="Bypass exists.", evidence_text="Hackers found a bypass.", relevance_score=0.8, source_quality_score=0.6, confidence=0.7, polarity="CONTRADICTS")
        db.add_all([e_a, e_b, e_c])
        await db.commit()
        
        print("\n--- 3. SYNTHESIZING BELIEFS ---")
        llm = FakeLLMProvider()
        # Mock the FakeLLM behavior to return specific IDs if needed, but our FakeLLM will just regex for IDs.
        # It'll grab the first as support, second as contradict.
        engine = BeliefService(db, llm)
        beliefs = await engine.synthesize_for_question("q_ada")
        
        b = beliefs[0]
        print(f"\nBelief: {b.statement}")
        print(f"Confidence: {b.confidence}")
        print(f"Status: {b.status}")
        
        print("\n--- 4. NEW CONTRADICTORY EVIDENCE ARRIVES ---")
        e_new = Evidence(id="e_new", question_id="q_ada", source_id="s_good", claim="Tool agents are highly vulnerable.", evidence_text="contradict", relevance_score=1.0, source_quality_score=1.0, confidence=1.0, polarity="CONTRADICTS")
        db.add(e_new)
        await db.commit()
        
        await engine.revise_beliefs(b.id, ["e_new"])
        
        mem = MemoryService(db)
        history = await mem.get_belief_history(b.id)
        
        await db.refresh(b)
        print(f"\nBefore: 0.6") # Hardcoded from FakeLLM
        print(f"After: {b.confidence}")
        print(f"Status: {b.status}")
        print(f"Reason: {history[-1].reason}")
        
        print("\n--- 5. BELIEF HISTORY ---")
        for i, rev in enumerate(history):
            print(f"Revision {i+1}: {rev.change_type} | {rev.previous_confidence} -> {rev.new_confidence} | {rev.reason}")

if __name__ == "__main__":
    asyncio.run(run_manual_test())
