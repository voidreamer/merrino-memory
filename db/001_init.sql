-- Merrino Memory schema initialization
create schema if not exists merrino_memory;

-- Enable pgvector
create extension if not exists vector;

-- Memory chunks with embeddings
create table merrino_memory.chunks (
    id uuid default gen_random_uuid() primary key,
    content text not null,
    source text not null,
    source_path text,
    source_date date,
    importance text default 'normal',
    tags text[] default '{}',
    embedding vector(384),
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create index idx_chunks_embedding on merrino_memory.chunks
    using ivfflat (embedding vector_cosine_ops) with (lists = 100);
create index idx_chunks_source on merrino_memory.chunks(source);
create index idx_chunks_source_date on merrino_memory.chunks(source_date);
create index idx_chunks_importance on merrino_memory.chunks(importance);
