import uuid
from datetime import date, datetime
from sqlalchemy import Column, String, Text, Date, ARRAY, DateTime
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, Field

from app.database import Base


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = {"schema": "merrino_memory"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content = Column(Text, nullable=False)
    source = Column(String, nullable=False)
    source_path = Column(String, nullable=True)
    source_date = Column(Date, nullable=True)
    importance = Column(String, default="normal")
    tags = Column(ARRAY(String), default=[])
    embedding = Column(Vector(384))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)


# --- Pydantic schemas ---

class IngestRequest(BaseModel):
    content: str
    source: str = "manual"
    source_path: str | None = None
    source_date: date | None = None
    importance: str = "normal"
    tags: list[str] = Field(default_factory=list)


class IngestFileRequest(BaseModel):
    file_path: str
    source: str = "file"
    source_date: date | None = None
    importance: str = "normal"
    tags: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    source: str | None = None
    importance: str | None = None


class ChunkResponse(BaseModel):
    id: str
    content: str
    source: str
    source_path: str | None
    source_date: date | None
    importance: str
    tags: list[str]
    created_at: datetime
    score: float | None = None

    class Config:
        from_attributes = True


class StatsResponse(BaseModel):
    total_chunks: int
    sources: dict[str, int]
    date_range: dict[str, str | None]
