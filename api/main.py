#!/usr/bin/env python3
"""Agent Memory API — OpenAI-compatible embeddings + semantic search over pgvector."""

import os
import uuid
from contextlib import asynccontextmanager
from datetime import date

import psycopg2
import psycopg2.pool
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# --- Config ---
DB_URL = os.environ.get("AGENT_MEMORY_DB_URL", "postgresql://postgres.blfitvvauoncoifrgvej:p3mfYQEtf3n@aws-1-ca-central-1.pooler.supabase.com:6543/postgres")
OLLAMA_URL = os.environ.get("AGENT_MEMORY_OLLAMA_URL", "http://localhost:11434/api/embeddings")
MODEL = os.environ.get("AGENT_MEMORY_MODEL", "nomic-embed-text")
SCHEMA = os.environ.get("AGENT_MEMORY_SCHEMA", "agent_memory")
DEFAULT_AGENT = os.environ.get("AGENT_MEMORY_DEFAULT_AGENT", "merrino")

pool = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = psycopg2.pool.ThreadedConnectionPool(1, 5, DB_URL)
    yield
    pool.closeall()


app = FastAPI(title="Agent Memory", version="1.0.0", lifespan=lifespan)


# --- Models ---
class SearchRequest(BaseModel):
    query: str
    agent_id: str | None = None
    top_k: int = 5
    min_similarity: float = 0.0


class SearchResult(BaseModel):
    content: str
    source: str
    source_path: str | None
    source_date: str | None
    similarity: float


class SearchResponse(BaseModel):
    results: list[SearchResult]
    agent_id: str
    query: str


class HealthResponse(BaseModel):
    status: str
    chunks: int
    agents: list[str]


# --- Helpers ---
def get_embedding(text: str) -> list[float]:
    try:
        r = requests.post(OLLAMA_URL, json={"model": MODEL, "prompt": text}, timeout=30)
        r.raise_for_status()
        return r.json()["embedding"]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ollama error: {e}")


# --- Routes ---
@app.get("/health", response_model=HealthResponse)
def health():
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT count(*) FROM {SCHEMA}.chunks")
        total = cur.fetchone()[0]
        cur.execute(f"SELECT DISTINCT agent_id FROM {SCHEMA}.chunks ORDER BY agent_id")
        agents = [row[0] for row in cur.fetchall()]
        return HealthResponse(status="ok", chunks=total, agents=agents)
    finally:
        pool.putconn(conn)


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest):
    agent_id = req.agent_id or DEFAULT_AGENT
    embedding = get_embedding(req.query)

    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT content, source, source_path, source_date,
                   1 - (embedding <=> %s::vector) as similarity
            FROM {SCHEMA}.chunks
            WHERE agent_id = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, (str(embedding), agent_id, str(embedding), req.top_k))

        results = []
        for row in cur.fetchall():
            sim = round(row[4], 4)
            if sim >= req.min_similarity:
                results.append(SearchResult(
                    content=row[0],
                    source=row[1],
                    source_path=row[2],
                    source_date=str(row[3]) if row[3] else None,
                    similarity=sim,
                ))
        return SearchResponse(results=results, agent_id=agent_id, query=req.query)
    finally:
        pool.putconn(conn)


@app.post("/index/trigger")
def trigger_index():
    """Trigger incremental indexing (runs synchronously — for cron/heartbeat use)."""
    import subprocess
    script = os.path.join(os.path.dirname(__file__), "..", "cli", "index_incremental.py")
    if not os.path.exists(script):
        raise HTTPException(status_code=404, detail="Incremental indexer not found")
    result = subprocess.run(["python3", script], capture_output=True, text=True, timeout=300)
    return {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8100)
