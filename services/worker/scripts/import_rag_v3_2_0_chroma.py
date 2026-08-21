from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer


SCRIPT_FILE = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_FILE.parents[3]

DEFAULT_INPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "rag"
    / "v3_2_0"
    / "meeting_analyst_rag_v3_2_0_frozen_candidate_500.jsonl"
)
DEFAULT_MANIFEST_FILE = (
    PROJECT_ROOT
    / "data"
    / "rag"
    / "v3_2_0"
    / "manifest.v3_2_0.json"
)
DEFAULT_DB_DIR = PROJECT_ROOT / "data" / "vector_db"

DATASET_VERSION = "meeting_analyst_rag_v3_2_0"
CHUNK_SCHEMA_VERSION = "rag-chunk-v3.2"
SCENARIO_TAXONOMY_VERSION = "meeting-scenario-9-v1"
CORPUS_STATUS = "FROZEN_CANDIDATE"
DEFAULT_COLLECTION = "meeting_analyst_rules_v3_2_0"
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
EXPECTED_COUNT = 500

PROTECTED_COLLECTIONS = {
    "meeting_analyst_rules",
    "meeting_analyst_rules_v2_dedup_125",
    "meeting_analyst_rules_v2_1",
    "meeting_analyst_rules_v2_1_1",
}

ALLOWED_METADATA_TYPES = (
    str,
    int,
    float,
    bool,
)


class ImportValidationError(RuntimeError):
    pass


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    return " ".join(str(value).strip().split())


def normalize_metadata_value(value: Any) -> str | int | float | bool:
    if isinstance(value, ALLOWED_METADATA_TYPES):
        return value

    if value is None:
        return ""

    if isinstance(value, list):
        return "|".join(normalize_text(item) for item in value)

    return normalize_text(value)


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"RAG manifest not found: {path}")

    manifest = json.loads(path.read_text(encoding="utf-8"))

    expected = {
        "dataset_version": DATASET_VERSION,
        "chunk_schema_version": CHUNK_SCHEMA_VERSION,
        "scenario_taxonomy_version": SCENARIO_TAXONOMY_VERSION,
        "corpus_status": CORPUS_STATUS,
        "expected_chunk_count": EXPECTED_COUNT,
        "default_collection": DEFAULT_COLLECTION,
    }

    for key, expected_value in expected.items():
        actual = manifest.get(key)
        if actual != expected_value:
            raise ImportValidationError(
                f"Manifest {key} must be {expected_value}, got {actual}"
            )

    return manifest


def build_embedding_text(item: dict[str, Any]) -> str:
    metadata = item.get("metadata", {})

    fields = [
        ("title", item.get("title")),
        ("dimension", metadata.get("dimension")),
        ("retrieval_pool", metadata.get("retrieval_pool")),
        ("scenario", metadata.get("scenario")),
        ("speech_act", metadata.get("speech_act")),
        ("subtype", metadata.get("subtype")),
        ("knowledge_type", metadata.get("knowledge_type")),
        ("confusable_with", metadata.get("confusable_with")),
        ("state", metadata.get("state")),
        ("content", item.get("content")),
    ]

    return "\n".join(
        f"{name}: {normalize_text(value)}"
        for name, value in fields
        if normalize_text(value)
    )


def validate_item(
    item: dict[str, Any],
    *,
    line_number: int,
) -> dict[str, Any]:
    chunk_id = normalize_text(item.get("chunk_id"))
    item_id = normalize_text(item.get("id"))
    title = normalize_text(item.get("title"))
    content = normalize_text(item.get("content"))
    metadata = item.get("metadata")

    if not chunk_id:
        raise ImportValidationError(f"Line {line_number}: missing chunk_id")

    if item_id and item_id != chunk_id:
        raise ImportValidationError(
            f"Line {line_number}: id and chunk_id mismatch for {chunk_id}"
        )

    if not title:
        raise ImportValidationError(f"Line {line_number}: {chunk_id} title is empty")

    if not content:
        raise ImportValidationError(f"Line {line_number}: {chunk_id} content is empty")

    if not isinstance(metadata, dict):
        raise ImportValidationError(
            f"Line {line_number}: {chunk_id} metadata must be object"
        )

    required_metadata = {
        "dataset_version": DATASET_VERSION,
        "chunk_schema_version": CHUNK_SCHEMA_VERSION,
        "scenario_taxonomy_version": SCENARIO_TAXONOMY_VERSION,
        "corpus_status": CORPUS_STATUS,
    }

    for key, expected_value in required_metadata.items():
        actual = normalize_text(metadata.get(key))
        if actual != expected_value:
            raise ImportValidationError(
                f"{chunk_id}: metadata {key} must be {expected_value}, got {actual}"
            )

    required_non_empty = [
        "dimension",
        "retrieval_pool",
        "scenario",
        "knowledge_type",
        "retrieval_version",
    ]

    for key in required_non_empty:
        if not normalize_text(metadata.get(key)):
            raise ImportValidationError(f"{chunk_id}: metadata {key} is empty")

    return item


def load_chunks(input_file: Path) -> list[dict[str, Any]]:
    if not input_file.exists():
        raise FileNotFoundError(f"RAG source file not found: {input_file}")

    chunks: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    with input_file.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError as error:
                raise ImportValidationError(
                    f"Invalid JSONL at line {line_number}: {error}"
                ) from error

            item = validate_item(item, line_number=line_number)
            chunk_id = normalize_text(item["chunk_id"])

            if chunk_id in seen_ids:
                raise ImportValidationError(f"Duplicate chunk_id: {chunk_id}")

            seen_ids.add(chunk_id)
            chunks.append(item)

    if len(chunks) != EXPECTED_COUNT:
        raise ImportValidationError(
            f"Expected {EXPECTED_COUNT} chunks, got {len(chunks)}"
        )

    return chunks


def make_chroma_metadata(item: dict[str, Any]) -> dict[str, str | int | float | bool]:
    metadata = item["metadata"]
    chroma_metadata: dict[str, str | int | float | bool] = {
        "chunk_id": normalize_text(item.get("chunk_id")),
        "id": normalize_text(item.get("id")),
        "title": normalize_text(item.get("title")),
    }

    for key, value in metadata.items():
        normalized = normalize_metadata_value(value)
        if not isinstance(normalized, ALLOWED_METADATA_TYPES):
            raise ImportValidationError(
                f"{item['chunk_id']}: metadata {key} cannot be written to Chroma"
            )
        chroma_metadata[key] = normalized

    return chroma_metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Import MeetMind RAG v3.2.0 frozen candidate into an independent "
            "Chroma collection."
        )
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_FILE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_FILE)
    parser.add_argument("--db-dir", type=Path, default=DEFAULT_DB_DIR)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete only the v3.2.0 target collection before import.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate source JSONL and metadata without writing Chroma.",
    )
    parser.add_argument(
        "--allow-download",
        action="store_true",
        help="Allow SentenceTransformer to download missing embedding model files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    input_file = args.input.resolve()
    manifest_file = args.manifest.resolve()
    db_dir = args.db_dir.resolve()
    collection_name = args.collection.strip()
    embedding_model_name = args.embedding_model.strip()

    load_manifest(manifest_file)

    if collection_name in PROTECTED_COLLECTIONS:
        raise ImportValidationError(
            f"Refusing to write protected collection: {collection_name}"
        )

    if collection_name != DEFAULT_COLLECTION:
        raise ImportValidationError(
            f"v3.2.0 import must target {DEFAULT_COLLECTION}, got {collection_name}"
        )

    chunks = load_chunks(input_file)
    ids = [normalize_text(item["chunk_id"]) for item in chunks]
    documents = [build_embedding_text(item) for item in chunks]
    metadatas = [make_chroma_metadata(item) for item in chunks]

    print("Project root:", PROJECT_ROOT)
    print("Input file:", input_file)
    print("Manifest:", manifest_file)
    print("Vector DB:", db_dir)
    print("Collection:", collection_name)
    print("Embedding model:", embedding_model_name)
    print("Embedding local files only:", not args.allow_download)
    print("Validated chunks:", len(chunks))
    print("Dataset version:", DATASET_VERSION)
    print("Chunk schema version:", CHUNK_SCHEMA_VERSION)
    print("Scenario taxonomy version:", SCENARIO_TAXONOMY_VERSION)
    print("Corpus status:", CORPUS_STATUS)

    if args.validate_only:
        print("\nRAG v3.2.0 validation success.")
        return 0

    print("\nLoading embedding model...")
    embedding_model = SentenceTransformer(
        embedding_model_name,
        local_files_only=not args.allow_download,
    )
    print("Embedding model loaded.")

    print("\nGenerating embeddings...")
    embeddings = embedding_model.encode(
        documents,
        normalize_embeddings=True,
        show_progress_bar=True,
    ).tolist()

    if len(embeddings) != EXPECTED_COUNT:
        raise ImportValidationError(f"Embedding count mismatch: {len(embeddings)}")

    db_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(db_dir))
    existing_names = {collection.name for collection in client.list_collections()}

    print("\nCollections before import:", sorted(existing_names))

    if args.reset:
        if collection_name in existing_names:
            client.delete_collection(collection_name)
            print("Deleted target collection:", collection_name)
        else:
            print("Target collection did not exist:", collection_name)

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={
            "description": "MeetMind Meeting Analyst RAG v3.2.0 frozen candidate",
            "dataset_version": DATASET_VERSION,
            "chunk_schema_version": CHUNK_SCHEMA_VERSION,
            "scenario_taxonomy_version": SCENARIO_TAXONOMY_VERSION,
            "corpus_status": CORPUS_STATUS,
            "retrieval_version": "meeting-rag-retrieval-v2",
            "embedding_model": embedding_model_name,
            "expected_count": EXPECTED_COUNT,
        },
    )

    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    actual_count = collection.count()
    if actual_count != EXPECTED_COUNT:
        raise ImportValidationError(
            f"Collection count must be {EXPECTED_COUNT}, got {actual_count}"
        )

    final_names = {collection.name for collection in client.list_collections()}
    missing_protected = PROTECTED_COLLECTIONS - final_names
    if missing_protected:
        print(
            "\nWarning: historical collections not found:",
            sorted(missing_protected),
        )

    print("\n============================")
    print("RAG v3.2.0 Import Success")
    print("============================")
    print("Imported:", len(ids))
    print("Collection count:", actual_count)
    print("Collection:", collection_name)
    print("DB path:", db_dir)
    print("Collections after import:", sorted(final_names))

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ImportValidationError,
        FileNotFoundError,
        ValueError,
        KeyError,
    ) as error:
        print(f"RAG v3.2.0 import failed: {error}", file=sys.stderr)
        raise SystemExit(1)
