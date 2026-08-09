from pydantic import BaseModel, Field
from typing import List

class GeneratedResearchQuestion(BaseModel):
    question: str = Field(..., description="The specific research question.")
    importance: float = Field(..., ge=0.0, le=1.0, description="Importance of the question (0.0 to 1.0).")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Current confidence in understanding (0.0 to 1.0).")

class GeneratedResearchThread(BaseModel):
    title: str = Field(..., description="A short, concise title for the research thread.")
    description: str = Field(..., description="A description of the thread's focus and scope.")
    priority: float = Field(..., ge=0.0, le=1.0, description="Priority of the thread (0.0 to 1.0).")
    questions: List[GeneratedResearchQuestion] = Field(..., min_length=2, max_length=4)

class GeneratedPersona(BaseModel):
    voice_style: str = Field(..., description="The consistent communication style.")
    technicality: float = Field(..., ge=0.0, le=1.0, description="How technical the persona is (0.0 to 1.0).")
    skepticism: float = Field(..., ge=0.0, le=1.0, description="Level of skepticism (0.0 to 1.0).")
    formality: float = Field(..., ge=0.0, le=1.0, description="Level of formality (0.0 to 1.0).")

    preferred_content_types: List[str] = Field(..., description="Types of content the persona prefers to read/produce.")
    avoided_content_types: List[str] = Field(..., description="Types of content the persona avoids.")

    editorial_principles: List[str] = Field(..., description="The persona's core editorial principles.")
    evidence_preferences: List[str] = Field(..., description="What constitutes good evidence for this persona.")

    research_threads: List[GeneratedResearchThread] = Field(..., min_length=3, max_length=5)
