import json
import argparse
import sys
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer


SCRIPT_FILE = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_FILE.parents[3]
WORKER_ROOT = SCRIPT_FILE.parents[1]
sys.path.insert(0, str(WORKER_ROOT))

from app.config import get_settings  # noqa: E402

MANIFEST_FILE = PROJECT_ROOT / "data" / "rag" / "meeting_analyst_rag_manifest.json"

DEFAULT_RAG_FILE = PROJECT_ROOT / "data" / "rag" / "meeting_analyst_rag_350_chunks.jsonl"
DEFAULT_DB_DIR = PROJECT_ROOT / "data" / "vector_db"


def build_embedding_text(item: dict) -> str:
    keywords = "、".join(item.get("keywords", []))

    return f"""
标题：{item.get("title", "")}
章节：{item.get("section", "")}
正文：{item.get("content", "")}
关键词：{keywords}
""".strip()


def main():
    parser = argparse.ArgumentParser(description="Import Meeting Analyst RAG chunks into Chroma.")
    parser.add_argument("--reset", action="store_true", help="Delete the target collection before upsert.")
    args = parser.parse_args()

    settings = get_settings()
    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    rag_file = PROJECT_ROOT / "data" / "rag" / manifest.get("source_file", DEFAULT_RAG_FILE.name)
    db_dir = Path(settings.rag_chroma_db_dir or DEFAULT_DB_DIR)
    collection_name = settings.rag_collection_name
    embedding_model_name = settings.rag_embedding_model

    print("Project root:", PROJECT_ROOT)
    print("RAG manifest:", MANIFEST_FILE)
    print("RAG file:", rag_file)
    print("Dataset version:", settings.rag_dataset_version)
    print("Chunk schema version:", settings.rag_chunk_schema_version)
    print("Vector DB:", db_dir)
    print("Collection:", collection_name)

    if not rag_file.exists():
        raise FileNotFoundError(f"RAG file not found: {rag_file}")

    print("\nLoading embedding model...")
    embedding_model = SentenceTransformer(embedding_model_name)
    print("Embedding model loaded.")

    client = chromadb.PersistentClient(path=str(db_dir))

    if args.reset:
        try:
            client.delete_collection(collection_name)
            print(f"Deleted old collection: {collection_name}")
        except Exception:
            print(f"No old collection to delete: {collection_name}")

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={
            "description": "Meeting Analyst RAG Rules",
            "dataset_version": settings.rag_dataset_version,
            "chunk_schema_version": settings.rag_chunk_schema_version,
            "embedding_model": embedding_model_name,
        },
    )

    ids = []
    documents = []
    metadatas = []

    seen_ids: set[str] = set()

    with rag_file.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSONL at line {line_number}: {exc}"
                ) from exc

            required_fields = [
                "chunk_id",
                "doc_id",
                "doc_type",
                "title",
                "section",
                "content",
                "keywords",
                "metadata",
            ]

            for field in required_fields:
                if field not in item:
                    raise ValueError(
                        f"Line {line_number}: missing field {field}"
                    )

            chunk_id = str(item["chunk_id"])
            if chunk_id in seen_ids:
                raise ValueError(f"Duplicate chunk_id in source file: {chunk_id}")
            seen_ids.add(chunk_id)

            embedding_text = build_embedding_text(item)
            metadata = item.get("metadata", {})

            ids.append(chunk_id)
            documents.append(embedding_text)

            metadatas.append({
                "chunk_id": chunk_id,
                "doc_id": item.get("doc_id", ""),
                "doc_type": item.get("doc_type", ""),
                "title": item.get("title", ""),
                "section": item.get("section", ""),
                "knowledge_type": metadata.get(
                    "knowledge_type",
                    item.get("doc_type", ""),
                ),
                "priority": metadata.get("priority", "medium"),
                "version": metadata.get("version", ""),
                "dataset_version": settings.rag_dataset_version,
                "chunk_schema_version": settings.rag_chunk_schema_version,
                "source": metadata.get("source", ""),
            })

    print(f"\nLoaded {len(ids)} chunks.")

    expected_count = int(manifest.get("expected_chunk_count", 350))
    if len(ids) != expected_count:
        print(f"Warning: expected {expected_count} chunks, got {len(ids)}")

    print("Generating embeddings...")

    embeddings = embedding_model.encode(
        documents,
        normalize_embeddings=True,
        show_progress_bar=True,
    ).tolist()

    print("Embeddings generated.")

    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    print("\n============================")
    print("RAG Import Success")
    print("============================")
    print("Imported:", len(ids))
    print("Collection count:", collection.count())
    print("Collection:", collection_name)
    print("DB path:", db_dir)


if __name__ == "__main__":
    main()
