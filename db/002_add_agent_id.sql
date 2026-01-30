-- Migration: Add agent_id column for multi-tenant support
-- Run this on existing installs that used the original merrino_memory schema.

-- 1. Rename schema if still using old name
ALTER SCHEMA merrino_memory RENAME TO agent_memory;

-- 2. Add agent_id column
ALTER TABLE agent_memory.chunks
    ADD COLUMN IF NOT EXISTS agent_id TEXT NOT NULL DEFAULT 'default';

-- 3. Add index on agent_id
CREATE INDEX IF NOT EXISTS idx_chunks_agent_id ON agent_memory.chunks(agent_id);
