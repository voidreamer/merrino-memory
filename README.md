# Agent Memory

A generic, agent-agnostic vector memory system using **pgvector** + **Ollama**.

Index markdown files, daily notes, and conversation transcripts into PostgreSQL with semantic embeddings, then search them with natural language queries. Works with any AI agent.

## Architecture

```
┌──────────────┐     ┌─────────┐     ┌──────────────────────┐
│  Source Files │────▶│  CLI    │────▶│  PostgreSQL + pgvec  │
│  .md / .jsonl │     │  Tools  │     │  agent_memory.chunks │
└──────────────┘     └────┬────┘     └──────────┬───────────┘
                          │                     │
                     ┌────▼────┐           ┌────▼────┐
                     │  Ollama │           │  Search │
                     │  embed  │◀──────────│  query  │
                     └─────────┘           └─────────┘
```

**Multi-tenant**: multiple agents share one database, isolated by `agent_id`.

## Prerequisites

- **PostgreSQL** with [pgvector](https://github.com/pgvector/pgvector) extension
- **Ollama** running locally with `nomic-embed-text` model
- **Python 3.11+**

```bash
# Pull the embedding model
ollama pull nomic-embed-text
```

## Quick Start

### 1. Create the schema

```bash
psql -f db/001_init.sql your_database
# For existing installs migrating from merrino_memory:
# psql -f db/002_add_agent_id.sql your_database
```

### 2. Configure

```bash
cp config.example.yaml config.yaml
# Edit config.yaml with your database URL and source paths
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Index your memories

```bash
# Full index
cd cli && python index.py

# Incremental (only new/modified files)
cd cli && python index_incremental.py
```

### 5. Search

```bash
cd cli && python search.py "what do I know about project X?"
cd cli && python search.py --top 10 --json "architecture decisions"
```

## Config Reference

Config is loaded from (in order):
1. `--config <path>` CLI flag
2. `AGENT_MEMORY_CONFIG` environment variable
3. `config.yaml` in current working directory

```yaml
agent_id: my-agent              # Unique identifier for this agent
db_url: postgresql://...        # PostgreSQL connection string
ollama_url: http://localhost:11434/api/embeddings  # Ollama API
model: nomic-embed-text         # Embedding model (768 dimensions)
schema: agent_memory            # Database schema name

sources:
  - path: /path/to/daily-notes  # Directory of markdown files
    type: markdown_dir

  - path: /path/to/MEMORY.md    # Single markdown file
    type: single_file
    source_label: memory_md     # Optional label (defaults to type)

  - path: /path/to/sessions     # Directory of JSONL transcripts
    type: transcript_dir
```

### Source Types

| Type | Description |
|------|-------------|
| `markdown_dir` | Directory of `.md` files — each file is chunked and indexed |
| `single_file` | Single markdown file |
| `transcript_dir` | Directory of `.jsonl` conversation transcripts |

### Transcript Formats

The transcript parser handles two JSONL formats:

```jsonl
{"role": "user", "content": "Hello"}
{"type": "message", "message": {"role": "assistant", "content": [{"type": "text", "text": "Hi!"}]}}
```

## Adding to Your AI Agent

### Clawdbot / Claude Code

Add to your agent's startup or tool config:

```bash
export AGENT_MEMORY_CONFIG=/path/to/config.yaml
python3 /path/to/cli/search.py --json --top 5 "your query"
```

### Any Agent

The search script outputs JSON with `--json`:

```json
[
  {
    "content": "...",
    "source": "daily_note",
    "source_path": "/path/to/file.md",
    "source_date": "2025-01-15",
    "similarity": 0.8432
  }
]
```

Integrate into any tool-calling agent by invoking the search CLI and parsing the JSON output.

## CLI Tools

| Script | Purpose |
|--------|---------|
| `cli/index.py` | Full re-index of all configured sources |
| `cli/index_incremental.py` | Index only new/modified files |
| `cli/search.py` | Semantic search over indexed chunks |

All scripts accept `--config <path>` to specify config file location.

## License

MIT
# Test commit from merrino sandbox 🐑
