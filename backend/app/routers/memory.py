from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import (
    Chunk,
    ChunkResponse,
    IngestRequest,
    IngestFileRequest,
    SearchRequest,
    StatsResponse,
)
from app.chunker import chunk_text
from app.embeddings import generate_embedding, generate_embeddings

router = APIRouter()


def _chunk_to_response(chunk: Chunk, score: float | None = None) -> ChunkResponse:
    return ChunkResponse(
        id=str(chunk.id),
        content=chunk.content,
        source=chunk.source,
        source_path=chunk.source_path,
        source_date=chunk.source_date,
        importance=chunk.importance,
        tags=chunk.tags or [],
        created_at=chunk.created_at,
        score=score,
    )


@router.post("/ingest")
async def ingest(req: IngestRequest, db: Session = Depends(get_session)):
    """Ingest text content: chunk it, embed it, store it."""
    chunks = chunk_text(req.content)
    if not chunks:
        raise HTTPException(400, "No content to ingest")

    embeddings = await generate_embeddings(chunks)

    stored = []
    for text_chunk, emb in zip(chunks, embeddings):
        chunk = Chunk(
            content=text_chunk,
            source=req.source,
            source_path=req.source_path,
            source_date=req.source_date,
            importance=req.importance,
            tags=req.tags,
            embedding=emb,
        )
        db.add(chunk)
        stored.append(chunk)

    db.commit()
    for c in stored:
        db.refresh(c)

    return {
        "status": "ok",
        "chunks_created": len(stored),
        "chunk_ids": [str(c.id) for c in stored],
    }


@router.post("/search")
async def search(req: SearchRequest, db: Session = Depends(get_session)):
    """Semantic search over memory chunks."""
    query_embedding = await generate_embedding(req.query)

    # Build query with cosine distance
    query = (
        db.query(
            Chunk,
            Chunk.embedding.cosine_distance(query_embedding).label("distance"),
        )
        .filter(Chunk.embedding.isnot(None))
    )

    if req.source:
        query = query.filter(Chunk.source == req.source)
    if req.importance:
        query = query.filter(Chunk.importance == req.importance)

    results = query.order_by("distance").limit(req.top_k).all()

    return {
        "results": [
            _chunk_to_response(chunk, score=1.0 - dist)
            for chunk, dist in results
        ]
    }


@router.post("/ingest-file")
async def ingest_file(req: IngestFileRequest, db: Session = Depends(get_session)):
    """Ingest a file by reading its content."""
    try:
        with open(req.file_path, "r") as f:
            content = f.read()
    except FileNotFoundError:
        raise HTTPException(404, f"File not found: {req.file_path}")
    except Exception as e:
        raise HTTPException(500, f"Error reading file: {e}")

    ingest_req = IngestRequest(
        content=content,
        source=req.source,
        source_path=req.file_path,
        source_date=req.source_date,
        importance=req.importance,
        tags=req.tags,
    )
    return await ingest(ingest_req, db)


@router.get("/stats")
async def stats(db: Session = Depends(get_session)):
    """Memory statistics."""
    total = db.query(func.count(Chunk.id)).scalar() or 0

    source_counts = (
        db.query(Chunk.source, func.count(Chunk.id))
        .group_by(Chunk.source)
        .all()
    )

    min_date = db.query(func.min(Chunk.source_date)).scalar()
    max_date = db.query(func.max(Chunk.source_date)).scalar()

    return StatsResponse(
        total_chunks=total,
        sources={s: c for s, c in source_counts},
        date_range={
            "earliest": str(min_date) if min_date else None,
            "latest": str(max_date) if max_date else None,
        },
    )


@router.delete("/chunks/{chunk_id}")
async def delete_chunk(chunk_id: UUID, db: Session = Depends(get_session)):
    """Delete a memory chunk."""
    chunk = db.query(Chunk).filter(Chunk.id == chunk_id).first()
    if not chunk:
        raise HTTPException(404, "Chunk not found")
    db.delete(chunk)
    db.commit()
    return {"status": "ok", "deleted": str(chunk_id)}
