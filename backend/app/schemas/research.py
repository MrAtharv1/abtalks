from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class GeneratedResearchQuery(BaseModel):
    query: str = Field(..., description="The exact search query to execute.")
    angle: str = Field(..., description="The angle or type of query (e.g. EMPIRICAL, TECHNICAL, OVERVIEW, COUNTEREVIDENCE).")
    reason: str = Field(..., description="Operational reason for this query.")

class GeneratedResearchQueries(BaseModel):
    queries: List[GeneratedResearchQuery] = Field(..., min_length=2, max_length=4)

class ExtractedEvidence(BaseModel):
    claim: str = Field(..., description="The specific claim made in the source.")
    evidence_text: str = Field(..., description="The verbatim or highly accurate supporting passage from the source.")
    context: str = Field(..., description="Minimal context to understand the evidence.")
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="Relevance to the research question.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in this evidence.")
    polarity: str = Field(..., description="SUPPORTS, CONTRADICTS, or NEUTRAL")

class GeneratedEvidenceExtraction(BaseModel):
    evidence: List[ExtractedEvidence] = Field(default_factory=list, description="Extracted evidence records. Empty if none found.")

class SearchResult(BaseModel):
    url: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    published_at: Optional[str] = None
    source_domain: Optional[str] = None

class FetchedDocument(BaseModel):
    url: str
    final_url: str
    content_type: str
    raw_content: bytes
    title: Optional[str] = None
