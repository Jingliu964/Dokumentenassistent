from pydantic import BaseModel
from typing import List, Optional


class IngestResponse(BaseModel):
    files_processed: int
    chunks_added: int


class QueryRequest(BaseModel):
    question: str
    top_k: Optional[int] = None


class Citation(BaseModel):
    source: str
    chunk_id: int


class QueryResponse(BaseModel):
    answer: str
    citations: List[Citation]


class UploadResponse(BaseModel):
    files_saved: int
    files_failed: int
    failures: List[str] = []
