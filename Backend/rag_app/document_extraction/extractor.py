"""PDF extraction into normalized blocks using LlamaCloud Parse."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from llama_cloud import LlamaCloud


def create_document_id(file_path: str | Path) -> str:
    """Create a stable identifier from the complete file contents."""
    digest = hashlib.sha256()
    with Path(file_path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return f"doc_{digest.hexdigest()[:12]}"


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return value


def _bounding_boxes(item: Any) -> list[dict[str, Any]]:
    return [_model_dump(box) for box in (getattr(item, "bbox", None) or [])]


def _page_content(result: Any, result_type: str, field: str) -> list[tuple[int, str]]:
    content = getattr(result, result_type, None)
    pages = getattr(content, "pages", None) or []
    extracted: list[tuple[int, str]] = []
    for page in pages:
        if getattr(page, "success", True) is False:
            continue
        text = str(getattr(page, field, "") or "").strip()
        if text:
            extracted.append((int(getattr(page, "page_number", 0)), text))
    return extracted


def _fallback_blocks(
    pages: list[tuple[int, str]], document_id: str
) -> list[dict[str, Any]]:
    """Create normalized blocks when structured items are not returned."""
    blocks: list[dict[str, Any]] = []
    sequence = 0
    text_count = 0
    table_count = 0
    for page_number, page_markdown in pages:
        for part in re.split(r"\n\s*\n", page_markdown):
            content = part.strip()
            if not content:
                continue
            sequence += 1
            common = {
                "block_id": f"{document_id}_block_{sequence:06d}",
                "document_id": document_id,
                "sequence": sequence,
                "page_number": page_number,
                "bounding_boxes": [],
            }
            heading = re.match(r"^(#{1,6})\s+(.+)$", content, flags=re.DOTALL)
            if heading:
                text_count += 1
                blocks.append(
                    common
                    | {
                        "type": "heading",
                        "text_id": f"{document_id}_text_{text_count:06d}",
                        "text": heading.group(2).strip(),
                        "heading_level": len(heading.group(1)),
                    }
                )
            elif "|" in content and "\n" in content:
                table_count += 1
                blocks.append(
                    common
                    | {
                        "type": "table",
                        "table_id": f"{document_id}_table_{table_count:06d}",
                        "table_markdown": content,
                    }
                )
            else:
                text_count += 1
                blocks.append(
                    common
                    | {
                        "type": "text",
                        "text_id": f"{document_id}_text_{text_count:06d}",
                        "text": content,
                    }
                )
    return blocks


def _structured_blocks(result: Any, document_id: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    counters = {"text": 0, "image": 0, "table": 0}
    pages = getattr(getattr(result, "items", None), "pages", None) or []

    for page in pages:
        if getattr(page, "success", True) is False:
            continue
        page_number = int(getattr(page, "page_number", 0))
        for item in getattr(page, "items", None) or []:
            item_type = str(getattr(item, "type", "") or "text").lower()
            sequence = len(blocks) + 1
            common = {
                "block_id": f"{document_id}_block_{sequence:06d}",
                "document_id": document_id,
                "sequence": sequence,
                "page_number": page_number,
                "bounding_boxes": _bounding_boxes(item),
                "label": item_type,
            }

            if item_type == "heading":
                text = str(getattr(item, "value", "") or getattr(item, "md", "")).strip()
                if not text:
                    continue
                counters["text"] += 1
                blocks.append(
                    common
                    | {
                        "type": "heading",
                        "text_id": f"{document_id}_text_{counters['text']:06d}",
                        "text": text.lstrip("# ").strip(),
                        "heading_level": max(
                            1, min(int(getattr(item, "level", 1) or 1), 6)
                        ),
                    }
                )
            elif item_type == "table":
                table_markdown = str(
                    getattr(item, "md", "") or getattr(item, "csv", "")
                ).strip()
                if not table_markdown:
                    continue
                counters["table"] += 1
                blocks.append(
                    common
                    | {
                        "type": "table",
                        "table_id": f"{document_id}_table_{counters['table']:06d}",
                        "table_markdown": table_markdown,
                        "table_csv": str(getattr(item, "csv", "") or ""),
                    }
                )
            elif item_type == "image":
                caption = str(
                    getattr(item, "caption", "") or getattr(item, "md", "")
                ).strip()
                counters["image"] += 1
                blocks.append(
                    common
                    | {
                        "type": "image",
                        "image_id": f"{document_id}_image_{counters['image']:06d}",
                        "caption": caption,
                        "source_url": str(getattr(item, "url", "") or ""),
                    }
                )
            else:
                text = str(
                    getattr(item, "value", "") or getattr(item, "md", "")
                ).strip()
                if not text:
                    continue
                counters["text"] += 1
                blocks.append(
                    common
                    | {
                        "type": "text",
                        "text_id": f"{document_id}_text_{counters['text']:06d}",
                        "text": text,
                    }
                )
    return blocks


def extract_document(
    pdf_path: str | Path,
    output_directory: str | Path,
    *,
    api_key: str,
    tier: str = "agentic",
    version: str = "latest",
    timeout_seconds: float = 600.0,
    organization_id: str | None = None,
    project_id: str | None = None,
    document_name: str | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """Parse a PDF with LlamaCloud and persist normalized extraction artifacts."""
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Only PDF documents are supported: {pdf_path.name}")
    if not api_key.strip() and client is None:
        raise RuntimeError("Missing required LlamaCloud setting: LLAMA_CLOUD_API_KEY")

    document_id = create_document_id(pdf_path)
    document_directory = Path(output_directory) / document_id
    document_directory.mkdir(parents=True, exist_ok=True)

    cloud = client or LlamaCloud(api_key=api_key)
    scope = {
        key: value
        for key, value in {
            "organization_id": organization_id,
            "project_id": project_id,
        }.items()
        if value
    }
    try:
        uploaded_file = cloud.files.create(file=pdf_path, purpose="parse", **scope)
        result = cloud.parsing.parse(
            file_id=uploaded_file.id,
            tier=tier,
            version=version,
            expand=["markdown", "text", "items"],
            timeout=timeout_seconds,
            **scope,
        )
    except Exception as exc:
        raise RuntimeError(f"LlamaCloud parsing failed: {exc}") from exc

    markdown_pages = _page_content(result, "markdown", "markdown")
    text_pages = _page_content(result, "text", "text")
    markdown = str(getattr(result, "markdown_full", "") or "").strip()
    text = str(getattr(result, "text_full", "") or "").strip()
    if not markdown:
        markdown = "\n\n".join(value for _, value in markdown_pages)
    if not text:
        text = "\n\n".join(value for _, value in text_pages)

    blocks = _structured_blocks(result, document_id)
    if not blocks:
        blocks = _fallback_blocks(markdown_pages or text_pages, document_id)
    if not blocks:
        raise RuntimeError("LlamaCloud completed parsing but returned no document content")

    paths = {
        "markdown_path": document_directory / "document.md",
        "text_path": document_directory / "document.txt",
        "blocks_path": document_directory / "blocks.json",
        "raw_llama_cloud_path": document_directory / "llama_cloud.json",
    }
    paths["markdown_path"].write_text(markdown, encoding="utf-8")
    paths["text_path"].write_text(text, encoding="utf-8")
    paths["blocks_path"].write_text(
        json.dumps(blocks, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    paths["raw_llama_cloud_path"].write_text(
        json.dumps(_model_dump(result), indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    metadata = {
        "document_id": document_id,
        "document_name": document_name or pdf_path.name,
        "parser": "llama_cloud",
        "llama_cloud_file_id": str(uploaded_file.id),
        "llama_cloud_job_id": str(getattr(getattr(result, "job", None), "id", "")),
        "parse_tier": tier,
        "parse_version": version,
        **{key: str(value) for key, value in paths.items()},
        "block_count": len(blocks),
        "text_count": sum(block["type"] in {"text", "heading"} for block in blocks),
        "image_count": sum(block["type"] == "image" for block in blocks),
        "table_count": sum(block["type"] == "table" for block in blocks),
    }
    (document_directory / "document_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return metadata
