from pydantic import BaseModel, Field
from datetime import datetime

class PersonaInput(BaseModel):
    name: str = Field(..., description="The name of the persona")
    domain: str = Field(..., description="The domain of expertise")

class AgentInitRequest(BaseModel):
    persona: PersonaInput

class AgentInitResponse(BaseModel):
    agentId: str

class AgentResponse(BaseModel):
    id: str
    status: str
    created_at: datetime
    persona: PersonaInput

    model_config = {"from_attributes": True}
from typing import List, Optional

class BeliefResponse(BaseModel):
    id: str
    statement: str
    confidence: float
    importance: float
    status: str
    model_config = {"from_attributes": True}

class EvidenceResponse(BaseModel):
    id: str
    claim: str
    evidence_text: str
    relevance_score: float
    source_quality_score: float
    confidence: float
    polarity: str
    source_url: Optional[str] = None
    model_config = {"from_attributes": True}

class SourceResponse(BaseModel):
    id: str
    url: str
    title: Optional[str]
    domain: Optional[str]
    retrieved_at: datetime
    model_config = {"from_attributes": True}

class QuestionResponse(BaseModel):
    id: str
    question: str
    status: str
    importance: float
    confidence: float
    evidence: List[EvidenceResponse] = []
    model_config = {"from_attributes": True}

class ThreadResponse(BaseModel):
    id: str
    title: str
    description: str
    status: str
    priority: float
    questions: List[QuestionResponse] = []
    beliefs: List[BeliefResponse] = []
    model_config = {"from_attributes": True}

class WorkspaceResponse(BaseModel):
    agent_id: str
    status: str
    persona: PersonaInput
    threads: List[ThreadResponse] = []
    sources: List[SourceResponse] = []
