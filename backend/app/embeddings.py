"""Embedding generation — abstract interface.

Currently uses a simple HTTP call to an OpenAI-compatible endpoint.
Will be swapped to local Ollama or sentence-transformers later.
"""

import os
import httpx
import numpy as np

EMBEDDING_API_URL = os.environ.get(
    "EMBEDDING_API_URL", "https://api.openai.com/v1/embeddings"
)
EMBEDDING_API_KEY = os.environ.get("EMBEDDING_API_KEY", "")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM = 384


async def generate_embedding(text: str) -> list[float]:
    """Generate a 384-dim embedding for the given text."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            EMBEDDING_API_URL,
            headers={
                "Authorization": f"Bearer {EMBEDDING_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": EMBEDDING_MODEL,
                "input": text,
                "dimensions": EMBEDDING_DIM,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["data"][0]["embedding"]


async def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for multiple texts."""
    if not texts:
        return []
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            EMBEDDING_API_URL,
            headers={
                "Authorization": f"Bearer {EMBEDDING_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": EMBEDDING_MODEL,
                "input": texts,
                "dimensions": EMBEDDING_DIM,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in data["data"]]
