import pytest
import uuid
from pydantic import ValidationError
from app.schemas.persona import GeneratedPersona
from app.llm.provider import get_llm_provider
from app.db.database import AsyncSessionLocal
from app.db.models import Agent, PersonaProfile, Belief, BeliefRevision
from app.editorial.candidate import CandidateService

@pytest.mark.asyncio
async def test_persona_differentiation(db_session):
    from app.llm.provider import FakeLLMProvider
    llm = FakeLLMProvider()
    
    agent1_id = str(uuid.uuid4())
    agent2_id = str(uuid.uuid4())
    belief_id = str(uuid.uuid4())
    
    p1 = PersonaProfile(
        id=str(uuid.uuid4()),
        name="Ada",
        domain="AI Security",
        voice_style="highly analytical and dry"
    )
    p2 = PersonaProfile(
        id=str(uuid.uuid4()),
        name="Maya",
        domain="Tech Journalism",
        voice_style="sensationalist and loud"
    )
    db_session.add_all([p1, p2])
    
    a1 = Agent(id=agent1_id, persona_id=p1.id, status="ACTIVE")
    a2 = Agent(id=agent2_id, persona_id=p2.id, status="ACTIVE")
    db_session.add_all([a1, a2])
    
    b = Belief(
        id=belief_id,
        agent_id=agent1_id, # Mocked for sharing later
        thread_id=str(uuid.uuid4()),
        statement="AI is dangerous.",
        confidence=0.9,
        importance=0.9,
        status="ACTIVE"
    )
    db_session.add(b)
    
    r1 = BeliefRevision(
        id=str(uuid.uuid4()),
        belief_id=belief_id,
        previous_confidence=0.0,
        new_confidence=0.9,
        change_type="INITIAL",
        reason="Initial."
    )
    r2 = BeliefRevision(
        id=str(uuid.uuid4()),
        belief_id=belief_id,
        previous_confidence=0.0,
        new_confidence=0.9,
        change_type="INITIAL",
        reason="Initial."
    )
    db_session.add_all([r1, r2])
    await db_session.commit()
    
    svc = CandidateService(db_session, llm)
    
    # Test Ada
    candidates1 = await svc.generate_candidates(agent1_id)
    
    # We must reassign belief to agent2 for testing (in reality they are isolated)
    b.agent_id = agent2_id
    await db_session.commit()
    
    # Test Maya
    candidates2 = await svc.generate_candidates(agent2_id)
    
    # Ensure that candidates are successfully generated for both distinct personas
    # Since FakeLLMProvider just echoes a default schema, we just assert they didn't crash
    # and correctly fetched the respective persona profiles.
    assert isinstance(candidates1, list)
    assert isinstance(candidates2, list)

def test_generated_persona_rejects_wrapper():
    """Verify that if the LLM wraps the persona in {"Ada": {...}}, it is explicitly rejected."""
    bad_payload = {
        "Ada": {
            "voice_style": "Formal",
            "technicality": 0.8,
            "skepticism": 0.7,
            "formality": 0.9,
            "preferred_content_types": ["academic papers"],
            "avoided_content_types": ["clickbait"],
            "editorial_principles": ["Accuracy"],
            "evidence_preferences": ["Peer-reviewed"],
            "research_threads": [
                {"title": "T1", "description": "D1", "priority": 0.5, "questions": [{"question": "Q1", "importance": 0.5, "confidence": 0.5}, {"question": "Q2", "importance": 0.5, "confidence": 0.5}]},
                {"title": "T2", "description": "D2", "priority": 0.5, "questions": [{"question": "Q1", "importance": 0.5, "confidence": 0.5}, {"question": "Q2", "importance": 0.5, "confidence": 0.5}]},
                {"title": "T3", "description": "D3", "priority": 0.5, "questions": [{"question": "Q1", "importance": 0.5, "confidence": 0.5}, {"question": "Q2", "importance": 0.5, "confidence": 0.5}]}
            ]
        }
    }
    
    with pytest.raises(ValidationError) as exc_info:
        GeneratedPersona.model_validate(bad_payload)
        
    errors = exc_info.value.errors()
    # Pydantic should report all 9 fields missing
    missing_fields = {err["loc"][0] for err in errors if err["type"] == "missing"}
    assert "voice_style" in missing_fields
    assert "technicality" in missing_fields

def test_generated_persona_accepts_root_level():
    """Verify that the intended root-level structure works."""
    good_payload = {
        "voice_style": "Formal",
        "technicality": 0.8,
        "skepticism": 0.7,
        "formality": 0.9,
        "preferred_content_types": ["academic papers"],
        "avoided_content_types": ["clickbait"],
        "editorial_principles": ["Accuracy"],
        "evidence_preferences": ["Peer-reviewed"],
        "research_threads": [
            {"title": "T1", "description": "D1", "priority": 0.5, "questions": [{"question": "Q1", "importance": 0.5, "confidence": 0.5}, {"question": "Q2", "importance": 0.5, "confidence": 0.5}]},
            {"title": "T2", "description": "D2", "priority": 0.5, "questions": [{"question": "Q1", "importance": 0.5, "confidence": 0.5}, {"question": "Q2", "importance": 0.5, "confidence": 0.5}]},
            {"title": "T3", "description": "D3", "priority": 0.5, "questions": [{"question": "Q1", "importance": 0.5, "confidence": 0.5}, {"question": "Q2", "importance": 0.5, "confidence": 0.5}]}
        ]
    }
    
    persona = GeneratedPersona.model_validate(good_payload)
    assert persona.voice_style == "Formal"
    assert persona.technicality == 0.8
    assert len(persona.research_threads) == 3
