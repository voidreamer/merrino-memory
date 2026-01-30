#!/usr/bin/env python3
"""Full indexer: indexes all configured sources into pgvector."""

import json
import re
import sys
import uuid
from datetime import date
from pathlib import Path

import psycopg2
import requests

from config import load_config, parse_config_arg


def get_embedding(text: str, cfg: dict) -> list[float]:
    r = requests.post(cfg["ollama_url"], json={"model": cfg["model"], "prompt": text})
    r.raise_for_status()
    return r.json()["embedding"]


def chunk_text(text: str, max_chars: int = 800) -> list[str]:
    paragraphs = re.split(r'\n\n+', text.strip())
    chunks, current = [], ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 2 > max_chars and current:
            chunks.append(current.strip())
            current = para
        else:
            current = current + "\n\n" + para if current else para
    if current.strip():
        chunks.append(current.strip())
    return [c for c in chunks if len(c) > 20]


def extract_date_from_filename(filename: str) -> date | None:
    match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
    return date.fromisoformat(match.group(1)) if match else None


def index_markdown_file(conn, filepath: Path, source: str, cfg: dict) -> int:
    text = filepath.read_text(encoding='utf-8')
    if len(text) < 30:
        return 0
    source_date = extract_date_from_filename(filepath.name)
    chunks = chunk_text(text)
    schema = cfg["schema"]
    agent_id = cfg["agent_id"]
    count = 0
    with conn.cursor() as cur:
        for chunk in chunks:
            embedding = get_embedding(chunk, cfg)
            cur.execute(f"""
                INSERT INTO {schema}.chunks
                (id, agent_id, content, source, source_path, source_date, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
            """, (str(uuid.uuid4()), agent_id, chunk, source, str(filepath), source_date, str(embedding)))
            count += 1
    conn.commit()
    return count


def parse_transcript_messages(filepath: Path) -> list[str]:
    """Parse transcript supporting both simple and nested message formats."""
    lines = filepath.read_text(encoding='utf-8').strip().split('\n')
    messages = []
    for line in lines:
        try:
            entry = json.loads(line)
            # Format 1: nested {type: "message", message: {role, content}}
            if entry.get('type') == 'message':
                msg = entry.get('message', {})
                role = msg.get('role', '')
                content = msg.get('content', '')
            else:
                # Format 2: simple {role, content}
                role = entry.get('role', '')
                content = entry.get('content', '')

            if isinstance(content, list):
                content = ' '.join(c.get('text', '') for c in content if c.get('type') == 'text')
            if content and role in ('user', 'assistant') and len(content) > 20:
                messages.append(f"[{role}] {content}")
        except json.JSONDecodeError:
            continue
    return messages


def index_transcript(conn, filepath: Path, cfg: dict) -> int:
    messages = parse_transcript_messages(filepath)
    if not messages:
        return 0
    full_text = '\n\n'.join(messages)
    chunks = chunk_text(full_text, max_chars=1000)
    source_date = extract_date_from_filename(filepath.stem)
    schema = cfg["schema"]
    agent_id = cfg["agent_id"]
    count = 0
    with conn.cursor() as cur:
        for chunk in chunks:
            embedding = get_embedding(chunk, cfg)
            cur.execute(f"""
                INSERT INTO {schema}.chunks
                (id, agent_id, content, source, source_path, source_date, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
            """, (str(uuid.uuid4()), agent_id, chunk, 'transcript', str(filepath), source_date, str(embedding)))
            count += 1
    conn.commit()
    return count


def main():
    config_path, args = parse_config_arg(sys.argv[1:])
    cfg = load_config(config_path)
    transcripts_only = '--transcripts-only' in args

    conn = psycopg2.connect(cfg["db_url"])
    total = 0

    for src in cfg["sources"]:
        path = Path(src["path"])
        src_type = src["type"]
        label = src.get("source_label", src_type)

        if not path.exists():
            print(f"  ⚠️  Skipping {path} (not found)")
            continue

        if src_type == "single_file" and not transcripts_only:
            n = index_markdown_file(conn, path, label, cfg)
            print(f"  {path.name}: {n} chunks")
            total += n

        elif src_type == "markdown_dir" and not transcripts_only:
            for f in sorted(path.glob("*.md")):
                n = index_markdown_file(conn, f, label, cfg)
                print(f"  {f.name}: {n} chunks")
                total += n

        elif src_type == "transcript_dir":
            if transcripts_only:
                with conn.cursor() as cur:
                    cur.execute(f"DELETE FROM {cfg['schema']}.chunks WHERE source = 'transcript' AND agent_id = %s", (cfg["agent_id"],))
                    print(f"  Cleared old transcript chunks")
                conn.commit()
            for f in sorted(path.glob("*.jsonl")):
                n = index_transcript(conn, f, cfg)
                print(f"  {f.name}: {n} chunks")
                total += n

    conn.close()
    print(f"\n✅ Indexed {total} total chunks for agent '{cfg['agent_id']}'")


if __name__ == "__main__":
    print("🧠 Indexing memories...\n")
    main()
