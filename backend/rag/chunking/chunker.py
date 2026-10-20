"""Paragraph-aware chunking with overlap. Pure Python, deterministic (stable chunk ids)."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


@dataclass
class Chunk:
    index: int
    text: str
    chunk_id: str


def chunk_text(text: str, *, doc_id: str, version: int, max_chars: int = 1200, overlap: int = 150) -> list[Chunk]:
    if overlap >= max_chars:
        raise ValueError("overlap must be smaller than max_chars")
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    buf = ""
    for para in paragraphs:
        if len(para) > max_chars:
            # Split long paragraphs on sentence boundaries, falling back to hard cuts.
            sentences = re.split(r"(?<=[.!?])\s+", para)
            for s in sentences:
                while len(s) > max_chars:
                    pieces.append((buf + " " + s[:max_chars]).strip() if buf else s[:max_chars])
                    buf, s = "", s[max_chars - overlap:]
                if len(buf) + len(s) + 1 > max_chars:
                    pieces.append(buf.strip())
                    buf = buf[-overlap:] + " " + s if overlap else s
                else:
                    buf = f"{buf} {s}" if buf else s
            continue
        if len(buf) + len(para) + 2 > max_chars and buf:
            pieces.append(buf.strip())
            buf = (buf[-overlap:] + "\n\n" + para) if overlap else para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
    if buf.strip():
        pieces.append(buf.strip())

    chunks = []
    for i, piece in enumerate(p for p in pieces if p):
        digest = hashlib.sha1(f"{doc_id}:{version}:{i}:{piece}".encode()).hexdigest()[:16]
        chunks.append(Chunk(index=i, text=piece, chunk_id=f"{doc_id}:v{version}:{i}:{digest}"))
    return chunks
