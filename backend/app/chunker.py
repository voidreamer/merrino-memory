"""Text chunking logic — split content into ~500 char chunks."""

import re

MAX_CHUNK_SIZE = 500
OVERLAP = 50


def chunk_text(text: str, max_size: int = MAX_CHUNK_SIZE) -> list[str]:
    """Split text into chunks by paragraphs, respecting max_size.
    
    Strategy:
    1. Split by double newlines (paragraphs)
    2. If a paragraph exceeds max_size, split by sentences
    3. Merge small consecutive chunks
    """
    text = text.strip()
    if not text:
        return []

    if len(text) <= max_size:
        return [text]

    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(para) > max_size:
            # Split long paragraphs by sentences
            if current:
                chunks.append(current.strip())
                current = ""
            sentences = re.split(r"(?<=[.!?])\s+", para)
            for sentence in sentences:
                if len(current) + len(sentence) + 1 > max_size:
                    if current:
                        chunks.append(current.strip())
                    current = sentence
                else:
                    current = f"{current} {sentence}".strip()
        elif len(current) + len(para) + 2 > max_size:
            if current:
                chunks.append(current.strip())
            current = para
        else:
            current = f"{current}\n\n{para}".strip()

    if current:
        chunks.append(current.strip())

    return [c for c in chunks if c]
