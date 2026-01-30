-- Agent Memory schema initialization
CREATE SCHEMA IF NOT EXISTS agent_memory;

-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Memory chunks with embeddings
CREATE TABLE agent_memory.chunks (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    agent_id TEXT NOT NULL DEFAULT 'default',
    content TEXT NOT NULL,
    source TEXT NOT NULL,
    source_path TEXT,
    source_date DATE,
    importance TEXT DEFAULT 'normal',
    tags TEXT[] DEFAULT '{}',
    embedding vector(768),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX idx_chunks_agent_id ON agent_memory.chunks(agent_id);
CREATE INDEX idx_chunks_source ON agent_memory.chunks(source);
CREATE INDEX idx_chunks_source_date ON agent_memory.chunks(source_date);
CREATE INDEX idx_chunks_importance ON agent_memory.chunks(importance);

-- IVFFlat index — create after inserting data (needs rows to build lists)
-- CREATE INDEX idx_chunks_embedding ON agent_memory.chunks
--     USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
