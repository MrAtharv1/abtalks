from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class PostResponse(BaseModel):
    id: str
    createdAt: datetime = Field(alias="createdAt", validation_alias="created_at")
    text: str
    rationale: Optional[str] = None
    sources: List[str] = Field(default_factory=list)
    status: str = "PUBLISHED"
    is_candidate: bool = False

    model_config = {"from_attributes": True, "populate_by_name": True}

class FeedResponse(BaseModel):
    posts: List[PostResponse]
