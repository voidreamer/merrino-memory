# 🐑🧠 Merrino Memory

Merrino's long-term memory — vector search over conversation transcripts and notes.

A RAG-based memory system that indexes conversation transcripts and notes into vector embeddings, stored in Supabase pgvector, searchable via API.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  API Client  │────▶│ API Gateway  │────▶│  AWS Lambda      │
│  (Merrino)   │◀────│  (HTTP API)  │◀────│  FastAPI+Mangum  │
└─────────────┘     └──────────────┘     └────────┬────────┘
                                                   │
                                          ┌────────▼────────┐
                                          │  Supabase        │
                                          │  pgvector        │
                                          │  (384-dim)       │
                                          └─────────────────┘
```

- **Backend:** Python FastAPI on AWS Lambda via Mangum
- **Database:** Supabase PostgreSQL with pgvector extension
- **Embeddings:** 384-dim vectors (all-MiniLM-L6-v2 compatible)
- **Infra:** Terraform (Lambda + API Gateway)
- **CI/CD:** GitHub Actions

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/ingest` | Ingest text content → chunk → embed → store |
| `POST` | `/api/search` | Semantic search over memory chunks |
| `POST` | `/api/ingest-file` | Ingest a file by path |
| `GET` | `/api/stats` | Memory statistics |
| `DELETE` | `/api/chunks/{id}` | Delete a memory chunk |
| `GET` | `/health` | Health check |

## Local Development

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Set env vars
export DATABASE_URL="postgresql://..."
export ENVIRONMENT=dev

# Run locally
uvicorn app.main:app --reload --port 8000
```

## Database Setup

Run the migration in `db/001_init.sql` against your Supabase instance.

## Deployment

Managed via Terraform and GitHub Actions.

```bash
cd infra
terraform init
terraform plan -var-file=prod.tfvars
terraform apply -var-file=prod.tfvars
```

## GitHub Secrets Required

| Secret | Description |
|--------|-------------|
| `AWS_ACCESS_KEY_ID` | AWS credentials for deployment |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials for deployment |
| `AWS_REGION` | `ca-central-1` |
| `DATABASE_URL` | Supabase PostgreSQL connection string |
| `SUPABASE_JWT_SECRET` | Supabase JWT secret for auth |

## Project Structure

```
backend/
  app/
    main.py          # FastAPI + Mangum handler
    database.py      # SQLAlchemy engine
    models.py        # Chunk model with pgvector
    embeddings.py    # Embedding generation
    chunker.py       # Text chunking logic
    routers/
      memory.py      # Memory API endpoints
      health.py      # Health check
infra/               # Terraform (Lambda + API Gateway)
db/                  # SQL migrations
.github/workflows/   # CI/CD
```

## License

Private — Merrino's brain belongs to Merrino 🐑
