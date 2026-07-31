"""PDF extraction into normalized blocks and related assets using Docling."""

import hashlib
import json
from pathlib import Path
from typing import Any

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import PictureItem, SectionHeaderItem, TableItem, TextItem


def create_document_id(file_path: str | Path) -> str:
    """Create a stable identifier from the complete file contents."""
    digest = hashlib.sha256()
    with Path(file_path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return f"doc_{digest.hexdigest()[:12]}"


def _page_number(item: Any) -> int | None:
    return item.prov[0].page_no if getattr(item, "prov", None) else None


def _bounding_box(item: Any) -> dict[str, float] | None:
    if not getattr(item, "prov", None) or item.prov[0].bbox is None:
        return None
    box = item.prov[0].bbox
    return {"left": box.l, "top": box.t, "right": box.r, "bottom": box.b}


def _label(item: Any) -> str | None:
    label = getattr(item, "label", None)
    return getattr(label, "value", str(label)) if label is not None else None


def extract_document(
    pdf_path: str | Path,
    output_directory: str | Path,
    *,
    document_name: str | None = None,
    enable_ocr: bool = True,
    image_scale: float = 2.0,
) -> dict[str, Any]:
    """Extract a PDF to markdown, JSON blocks, images, tables, and metadata."""
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Only PDF documents are supported: {pdf_path.name}")

    document_id = create_document_id(pdf_path)
    document_directory = Path(output_directory) / document_id
    images_directory = document_directory / "images"
    tables_directory = document_directory / "tables"
    images_directory.mkdir(parents=True, exist_ok=True)
    tables_directory.mkdir(parents=True, exist_ok=True)

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = enable_ocr
    pipeline_options.generate_picture_images = True
    pipeline_options.images_scale = image_scale
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    document = converter.convert(pdf_path).document

    blocks: list[dict[str, Any]] = []
    markdown_parts: list[str] = []
    counters = {"text": 0, "image": 0, "table": 0}

    for sequence, (item, level) in enumerate(document.iterate_items(), start=1):
        common = {
            "block_id": f"{document_id}_block_{sequence:06d}",
            "document_id": document_id,
            "sequence": sequence,
            "page_number": _page_number(item),
            "bounding_box": _bounding_box(item),
            "label": _label(item),
        }

        if isinstance(item, PictureItem):
            counters["image"] += 1
            image_id = f"{document_id}_image_{counters['image']:06d}"
            image_path = images_directory / f"{image_id}.png"
            image = item.get_image(document)
            if image is not None:
                image.save(image_path, format="PNG")
            blocks.append(
                common
                | {
                    "type": "image",
                    "image_id": image_id,
                    "image_filename": image_path.name,
                    "image_path": str(image_path),
                }
            )
            markdown_parts.append(f'<image-ref id="{image_id}" />')
        elif isinstance(item, TableItem):
            counters["table"] += 1
            table_id = f"{document_id}_table_{counters['table']:06d}"
            table_path = tables_directory / f"{table_id}.csv"
            dataframe = item.export_to_dataframe(doc=document)
            dataframe.to_csv(table_path, index=False)
            table_markdown = dataframe.to_markdown(index=False)
            blocks.append(
                common
                | {
                    "type": "table",
                    "table_id": table_id,
                    "table_filename": table_path.name,
                    "table_path": str(table_path),
                    "table_markdown": table_markdown,
                }
            )
            markdown_parts.extend((f'<table-ref id="{table_id}" />', table_markdown))
        elif isinstance(item, (SectionHeaderItem, TextItem)):
            text = item.text.strip()
            if not text:
                continue
            counters["text"] += 1
            block_type = "heading" if isinstance(item, SectionHeaderItem) else "text"
            block = common | {
                "type": block_type,
                "text_id": f"{document_id}_text_{counters['text']:06d}",
                "text": text,
            }
            if block_type == "heading":
                block["heading_level"] = max(1, min(int(level or 1), 6))
                markdown_parts.append(f"{'#' * block['heading_level']} {text}")
            else:
                markdown_parts.append(text)
            blocks.append(block)

    paths = {
        "markdown_path": document_directory / "document.md",
        "blocks_path": document_directory / "blocks.json",
        "raw_docling_path": document_directory / "docling.json",
    }
    paths["markdown_path"].write_text("\n\n".join(markdown_parts), encoding="utf-8")
    paths["blocks_path"].write_text(
        json.dumps(blocks, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    paths["raw_docling_path"].write_text(
        json.dumps(document.export_to_dict(), indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    metadata = {
        "document_id": document_id,
        "document_name": document_name or pdf_path.name,
        **{key: str(value) for key, value in paths.items()},
        "images_directory": str(images_directory),
        "tables_directory": str(tables_directory),
        "block_count": len(blocks),
        "text_count": counters["text"],
        "image_count": counters["image"],
        "table_count": counters["table"],
    }
    (document_directory / "document_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return metadata
