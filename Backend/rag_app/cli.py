"""Command-line interface for local extraction, ingestion, and querying."""

import argparse
import json
from pathlib import Path

from .core.config import get_settings
from .document_extraction.chunking import chunk_document
from .document_extraction.extractor import extract_document
from .database.repository import PostgresDocumentRepository
from .rag_pipeline.service import RAGService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Enterprise RAG backend commands")
    commands = parser.add_subparsers(dest="command", required=True)

    extract = commands.add_parser("extract", help="Extract a PDF without indexing it")
    extract.add_argument("pdf", type=Path)
    extract.add_argument("--output", type=Path, default=Path("Backend/data/documents"))

    chunk = commands.add_parser("chunk", help="Chunk a previously extracted document")
    chunk.add_argument("document_directory", type=Path)

    ingest = commands.add_parser("ingest", help="Extract, chunk, embed, and index a PDF")
    ingest.add_argument("pdf", type=Path)
    ingest.add_argument("--namespace")

    query = commands.add_parser("query", help="Ask a question against indexed documents")
    query.add_argument("question")
    query.add_argument("--top-k", type=int)
    query.add_argument("--namespace")
    query.add_argument(
        "--search-mode", choices=("hybrid", "semantic", "keyword"), default="hybrid"
    )

    keyword = commands.add_parser("keyword-search", help="Search PostgreSQL chunk text")
    keyword.add_argument("query")
    keyword.add_argument("--top-k", type=int)
    keyword.add_argument("--namespace")
    keyword.add_argument("--document-id")

    commands.add_parser("init-index", help="Create or validate the configured Pinecone index")
    commands.add_parser("init-db", help="Create the PostgreSQL document-search schema")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = get_settings()
    if args.command == "extract":
        result = extract_document(args.pdf, args.output)
    elif args.command == "chunk":
        result = [chunk.model_dump() for chunk in chunk_document(
            args.document_directory,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )]
    elif args.command == "init-db":
        repository = PostgresDocumentRepository(settings)
        repository.initialize_schema()
        result = {"status": "ok", "database": settings.postgres_database}
    else:
        service = RAGService(settings)
        if args.command == "ingest":
            result = service.ingest_pdf(args.pdf, namespace=args.namespace).model_dump()
        elif args.command == "query":
            result = service.answer(
                args.question,
                top_k=args.top_k,
                namespace=args.namespace,
                search_mode=args.search_mode,
            ).model_dump()
        elif args.command == "keyword-search":
            result = [
                item.model_dump()
                for item in service.keyword_search(
                    args.query,
                    top_k=args.top_k,
                    namespace=args.namespace,
                    document_id=args.document_id,
                )
            ]
        else:
            description = service.vector_store.ensure_index()
            result = description.to_dict() if hasattr(description, "to_dict") else str(description)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
