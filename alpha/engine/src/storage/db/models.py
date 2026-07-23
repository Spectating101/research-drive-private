from datetime import datetime
from typing import List, Optional, Dict
from pydantic import BaseModel, Field

class Paper(BaseModel):
    """Paper metadata model."""
    id: str
    filename: str
    content_type: str
    size: int
    created_at: datetime
    status: str = "pending"
    tags: List[str] = Field(default_factory=list)
    metadata: Dict = Field(default_factory=dict)

class TextChunk(BaseModel):
    """Model for text chunks."""
    content: str
    index: int
    metadata: Dict = Field(default_factory=dict)

class ProcessedPaper(BaseModel):
    """Model for processed paper content."""
    id: str
    content: str
    chunks: List[TextChunk] = Field(default_factory=list)
    summary: Optional[str] = None
    vector_id: Optional[str] = None
    processed_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict = Field(default_factory=dict)

class SearchResult(BaseModel):
    """Model for search results."""
    paper_id: str
    score: float
    content: str
    metadata: Dict = Field(default_factory=dict)

class ResearchSession(BaseModel):
    """Model for research sessions."""
    id: str
    user_id: str
    topic: str
    papers: List[str] = Field(default_factory=list)
    notes: List[Dict] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "active"
    progress: Dict = Field(default_factory=dict)
    context: Dict = Field(default_factory=dict)
    synthesis: Optional[Dict] = None
    error: Optional[str] = None

class ResponseWithCitations(BaseModel):
    query: str
    answer: str
    citations: List[dict]
    user_profile: dict
    timestamp: str