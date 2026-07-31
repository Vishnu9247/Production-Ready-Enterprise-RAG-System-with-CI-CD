"""Deterministic, structure-aware chunking for extracted documents."""

import json
import re
from pathlib import Path
from typing import Any, Iterable

from ..core.schemas import Chunk


def _split_long_text(text: str, size: int, overlap: int) -> list[str]:
    """Split large text at word boundaries with character overlap."""
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) <= size:
        return [text] if text else []
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n", start, end), text.rfind(" ", start, end))
            if boundary > start + size // 2:
                end = boundary
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return pieces


def _unique(values: Iterable[Any]) -> list[Any]:
    return list(dict.fromkeys(value for value in values if value is not None and value != ""))


def chunk_document(
    document_directory: str | Path,
    *,
    chunk_size: int = 1800,
    chunk_overlap: int = 200,
    output_name: str = "chunks.json",
) -> list[Chunk]:
    """Create retrieval chunks from an extraction output directory."""
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")
    directory = Path(document_directory)
    blocks = json.loads((directory / "blocks.json").read_text(encoding="utf-8"))
    document_metadata = json.loads(
        (directory / "document_metadata.json").read_text(encoding="utf-8")
    )
    document_id = document_metadata["document_id"]
    headings: list[str] = []
    units: list[dict[str, Any]] = []

    for block in blocks:
        block_type = block.get("type")
        if block_type == "heading":
            level = max(1, int(block.get("heading_level", 1)))
            headings = headings[: level - 1]
            headings.append(block.get("text", "").strip())
            continue
        if block_type == "text":
            text = block.get("text", "").strip()
        elif block_type == "table":
            text = block.get("table_markdown", "").strip()
        elif block_type == "image":
            text = block.get("caption", "").strip()
        else:
            continue
        if text:
            units.append(
                {
                    "text": text,
                    "headings": list(headings),
                    "block_id": block.get("block_id"),
                    "text_id": block.get("text_id"),
                    "table_id": block.get("table_id"),
                    "page_number": block.get("page_number"),
                }
            )

    raw_chunks: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []

    def flush() -> None:
        if not current:
            return
        prefix = " > ".join(current[0]["headings"])
        body = "\n\n".join(unit["text"] for unit in current)
        raw_chunks.append({"text": f"{prefix}\n\n{body}" if prefix else body, "units": list(current)})
        current.clear()

    for unit in units:
        prefix = " > ".join(unit["headings"])
        proposed = "\n\n".join(
            ([prefix] if prefix else []) + [item["text"] for item in current] + [unit["text"]]
        )
        if current and len(proposed) > chunk_size:
            flush()
        unit_size = chunk_size - min(len(prefix) + 2, chunk_size // 3)
        if len(unit["text"]) > unit_size:
            flush()
            for piece in _split_long_text(unit["text"], unit_size, chunk_overlap):
                raw_chunks.append(
                    {"text": f"{prefix}\n\n{piece}" if prefix else piece, "units": [unit]}
                )
        else:
            current.append(unit)
    flush()

    chunks: list[Chunk] = []
    for index, raw in enumerate(raw_chunks, start=1):
        source_units = raw["units"]
        text = raw["text"].strip()
        metadata = {
            "document_id": document_id,
            "document_name": document_metadata.get("document_name", ""),
            "chunk_index": index,
            "character_count": len(text),
            "word_count": len(text.split()),
            "chunking_method": "structure_aware",
            "headings": _unique(h for unit in source_units for h in unit["headings"]),
            "block_ids": _unique(unit["block_id"] for unit in source_units),
            "text_ids": _unique(unit["text_id"] for unit in source_units),
            "table_ids": _unique(unit["table_id"] for unit in source_units),
            "page_numbers": _unique(unit["page_number"] for unit in source_units),
        }
        chunks.append(
            Chunk(
                chunk_id=f"{document_id}_chunk_{index:06d}", text=text, metadata=metadata
            )
        )

    (directory / output_name).write_text(
        json.dumps([chunk.model_dump() for chunk in chunks], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return chunks
