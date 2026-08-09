from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class GeneratedEditorialCandidate(BaseModel):
    headline: str
    summary: str
    editorial_significance: float
    relevance_score: float

class GeneratedEditorialRationale(BaseModel):
    why_selected: str
    why_now: str
    why_not_alternatives: str
    memory_used: str
    belief_change: str
    evidence_basis: str

class GeneratedPost(BaseModel):
    text: str = Field(..., min_length=150, description="The actual text content of the post. MUST be a comprehensive, long-form paragraph at least 150 characters long.")
    editorial_angle: str
    fact_claims: List[str]
    interpretation: str
    uncertainty_level: str
    rationale: GeneratedEditorialRationale
    source_ids: List[str] # The LLM will pick from the available Evidence source IDs
