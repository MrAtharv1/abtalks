from pydantic import BaseModel, Field
from typing import List, Optional

class GeneratedBelief(BaseModel):
    statement: str = Field(..., description="A concise, specific proposition supported by evidence.")
    scope: str = Field(..., description="The scope where this proposition applies (e.g. general, specific timeframe, specific architecture).")
    importance: float = Field(..., ge=0.0, le=1.0, description="How consequential this belief is to the agent's research agenda.")
    initial_confidence: float = Field(..., ge=0.0, le=1.0, description="Initial confidence based solely on the supplied evidence.")
    supporting_evidence_ids: List[str] = Field(default_factory=list, description="List of IDs for evidence that supports this belief.")
    contradicting_evidence_ids: List[str] = Field(default_factory=list, description="List of IDs for evidence that contradicts this belief.")
    qualifying_evidence_ids: List[str] = Field(default_factory=list, description="List of IDs for evidence that qualifies this belief.")

class GeneratedBeliefSynthesis(BaseModel):
    beliefs: List[GeneratedBelief] = Field(default_factory=list, description="The list of synthesized beliefs.")
    unresolved_questions: List[str] = Field(default_factory=list, description="Any derived questions reflecting remaining uncertainty.")

class EvidenceAnalysis(BaseModel):
    evidence_id: str = Field(..., description="The ID of the new evidence being analyzed.")
    relationship: str = Field(..., description="SUPPORTS, CONTRADICTS, QUALIFIES, or UNRELATED")
    reason: str = Field(..., description="Brief reason for this classification.")

class BeliefRevisionAnalysis(BaseModel):
    belief_id: str = Field(..., description="The ID of the existing belief being revised.")
    analyses: List[EvidenceAnalysis] = Field(default_factory=list, description="Semantic interpretation of new evidence against this belief.")
