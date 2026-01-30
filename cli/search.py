#!/usr/bin/env python3
"""Memory search CLI — semantic search over indexed chunks.

Usage:
    python3 search.py "what do I know about Stripe?"
    python3 search.py --top 5 --json "HeyBub architecture"
    python3 search.py --config /path/to/config.yaml "query"
"""

import json
import sys

import psycopg2
import requests

from config import load_config, parse_config_arg


def search(query: str, top_k: int, cfg: dict) -> list[dict]:
    r = requests.post(cfg["ollama_url"], json={"model": cfg["model"], "prompt": query})
    r.raise_for_status()
    embedding = r.json()["embedding"]

    schema = cfg["schema"]
    agent_id = cfg["agent_id"]

    conn = psycopg2.connect(cfg["db_url"])
    cur = conn.cursor()
    cur.execute(f"""
        SELECT content, source, source_path, source_date,
               1 - (embedding <=> %s::vector) AS similarity
        FROM {schema}.chunks
        WHERE agent_id = %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """, (str(embedding), agent_id, str(embedding), top_k))

    results = []
    for row in cur.fetchall():
        results.append({
            "content": row[0],
            "source": row[1],
            "source_path": row[2],
            "source_date": str(row[3]) if row[3] else None,
            "similarity": round(row[4], 4),
        })

    conn.close()
    return results


def main():
    config_path, args = parse_config_arg(sys.argv[1:])
    cfg = load_config(config_path)

    top_k = 5
    json_output = False

    if "--top" in args:
        idx = args.index("--top")
        top_k = int(args[idx + 1])
        args = args[:idx] + args[idx + 2:]

    if "--json" in args:
        args.remove("--json")
        json_output = True

    query = " ".join(args)
    if not query:
        print("Usage: search.py [--config PATH] [--top N] [--json] <query>")
        sys.exit(1)

    results = search(query, top_k, cfg)

    if json_output:
        print(json.dumps(results, indent=2))
    else:
        print(f"🔍 Query: \"{query}\" (top {top_k})\n")
        for i, r in enumerate(results, 1):
            print(f"--- [{i}] sim={r['similarity']} | {r['source']} | {r['source_date']} ---")
            print(r["content"][:500])
            print()


if __name__ == "__main__":
    main()
