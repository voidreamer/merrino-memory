#!/usr/bin/env python3
"""Incremental indexer: only indexes new/modified files since last run."""

import json
import re
import sys
import uuid
from datetime import date, datetime, timezone
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


def file_mtime_utc(filepath: Path) -> datetime:
    return datetime.fromtimestamp(filepath.stat().st_mtime, tz=timezone.utc)


def get_indexed_state(conn, cfg: dict) -> dict[str, datetime]:
    schema = cfg["schema"]
    agent_id = cfg["agent_id"]
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT source_path, MAX(created_at)
            FROM {schema}.chunks
            WHERE agent_id = %s
            GROUP BY source_path
        """, (agent_id,))
        return {row[0]: row[1] for row in cur.fetchall()}


def delete_chunks_for(conn, source_path: str, cfg: dict) -> int:
    schema = cfg["schema"]
    agent_id = cfg["agent_id"]
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {schema}.chunks WHERE source_path = %s AND agent_id = %s", (source_path, agent_id))
        n = cur.rowcount
    conn.commit()
    return n


def index_markdown_chunks(conn, filepath: Path, source: str, cfg: dict) -> int:
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


def index_transcript_chunks(conn, filepath: Path, cfg: dict) -> int:
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


def collect_files(cfg: dict) -> list[tuple[Path, str]]:
    files = []
    for src in cfg["sources"]:
        path = Path(src["path"])
        src_type = src["type"]
        label = src.get("source_label", src_type)
        if not path.exists():
            continue
        if src_type == "single_file":
            files.append((path, label))
        elif src_type == "markdown_dir":
            for f in sorted(path.glob("*.md")):
                files.append((f, label))
        elif src_type == "transcript_dir":
            for f in sorted(path.glob("*.jsonl")):
                files.append((f, 'transcript'))
    return files


def main():
    config_path, args = parse_config_arg(sys.argv[1:])
    cfg = load_config(config_path)

    conn = psycopg2.connect(cfg["db_url"])
    indexed_state = get_indexed_state(conn, cfg)
    all_files = collect_files(cfg)

    new_files = 0
    updated_files = 0
    chunks_added = 0
    chunks_deleted = 0

    for filepath, source_type in all_files:
        path_str = str(filepath)
        mtime = file_mtime_utc(filepath)

        if path_str in indexed_state:
            last_indexed = indexed_state[path_str]
            if last_indexed.tzinfo is None:
                last_indexed = last_indexed.replace(tzinfo=timezone.utc)
            if mtime <= last_indexed:
                continue
            deleted = delete_chunks_for(conn, path_str, cfg)
            chunks_deleted += deleted
            if source_type == 'transcript':
                n = index_transcript_chunks(conn, filepath, cfg)
            else:
                n = index_markdown_chunks(conn, filepath, source_type, cfg)
            chunks_added += n
            updated_files += 1
            print(f"  ♻️  {filepath.name}: {deleted} old → {n} new chunks")
        else:
            if source_type == 'transcript':
                n = index_transcript_chunks(conn, filepath, cfg)
            else:
                n = index_markdown_chunks(conn, filepath, source_type, cfg)
            if n > 0:
                chunks_added += n
                new_files += 1
                print(f"  ✨ {filepath.name}: {n} chunks")

    conn.close()

    if new_files == 0 and updated_files == 0:
        print("Nothing new to index.")
    else:
        print(f"\n✅ {new_files} new, {updated_files} updated | +{chunks_added} / -{chunks_deleted} chunks (agent: {cfg['agent_id']})")


if __name__ == "__main__":
    print("🧠 Incremental memory index...\n")
    main()
