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
    / "v2_1"
    / "meeting_analyst_rag_v2_1_86.jsonl"
)

DEFAULT_DB_DIR = PROJECT_ROOT / "data" / "vector_db"

DEFAULT_COLLECTION = "meeting_analyst_rules_v2_1"
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"

EXPECTED_COUNT = 86

ALLOWED_RUNTIME_LAYERS = {
    "POLICY_FIXED",
    "RAG_DYNAMIC",
    "RAG_SCENARIO",
}


class ImportValidationError(RuntimeError):
    pass


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    return " ".join(str(value).strip().split())


def build_embedding_text(item: dict[str, Any]) -> str:
    metadata = item.get("metadata", {})

    title = normalize_text(item.get("title"))
    content = normalize_text(item.get("content"))

    runtime_layer = normalize_text(
        metadata.get("runtime_layer")
    )

    scenario = normalize_text(
        metadata.get("scenario")
    )

    dimension = normalize_text(
        metadata.get("dimension")
    )

    knowledge_type = normalize_text(
        metadata.get("knowledge_type")
    )

    return "\n".join(
        [
            f"标题：{title}",
            f"运行层：{runtime_layer}",
            f"会议场景：{scenario}",
            f"目标维度：{dimension}",
            f"知识类型：{knowledge_type}",
            f"规则正文：{content}",
        ]
    )


def load_chunks(
    input_file: Path,
) -> list[dict[str, Any]]:
    if not input_file.exists():
        raise FileNotFoundError(
            f"RAG source file not found: {input_file}"
        )

    chunks: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    with input_file.open(
        "r",
        encoding="utf-8",
    ) as file:
        for line_number, line in enumerate(
            file,
            start=1,
        ):
            line = line.strip()

            if not line:
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError as error:
                raise ImportValidationError(
                    f"Invalid JSONL at line "
                    f"{line_number}: {error}"
                ) from error

            chunk_id = normalize_text(
                item.get("chunk_id")
                or item.get("id")
            )

            title = normalize_text(
                item.get("title")
            )

            content = normalize_text(
                item.get("content")
            )

            metadata = item.get("metadata")

            if not chunk_id:
                raise ImportValidationError(
                    f"Line {line_number}: "
                    "missing chunk_id"
                )

            if chunk_id in seen_ids:
                raise ImportValidationError(
                    f"Duplicate chunk_id: {chunk_id}"
                )

            if not title:
                raise ImportValidationError(
                    f"Line {line_number}: "
                    f"{chunk_id} title is empty"
                )

            if not content:
                raise ImportValidationError(
                    f"Line {line_number}: "
                    f"{chunk_id} content is empty"
                )

            if not isinstance(metadata, dict):
                raise ImportValidationError(
                    f"Line {line_number}: "
                    f"{chunk_id} metadata must be object"
                )

            runtime_layer = normalize_text(
                metadata.get("runtime_layer")
            )

            if runtime_layer not in (
                ALLOWED_RUNTIME_LAYERS
            ):
                raise ImportValidationError(
                    f"{chunk_id}: invalid "
                    f"runtime_layer={runtime_layer}"
                )

            seen_ids.add(chunk_id)
            chunks.append(item)

    if len(chunks) != EXPECTED_COUNT:
        raise ImportValidationError(
            f"Expected {EXPECTED_COUNT} chunks, "
            f"got {len(chunks)}"
        )

    return chunks


def make_chroma_metadata(
    item: dict[str, Any],
) -> dict[str, str]:
    metadata = item["metadata"]

    return {
        "chunk_id": normalize_text(
            item.get("chunk_id")
            or item.get("id")
        ),
        "title": normalize_text(
            item.get("title")
        ),
        "runtime_layer": normalize_text(
            metadata.get("runtime_layer")
        ),
        "layer": normalize_text(
            metadata.get("layer")
        ),
        "scenario": normalize_text(
            metadata.get("scenario")
        ),
        "dimension": normalize_text(
            metadata.get("dimension")
        ),
        "knowledge_type": normalize_text(
            metadata.get("knowledge_type")
        ),
        "priority": normalize_text(
            metadata.get("priority")
        ),
        "version": normalize_text(
            metadata.get("version")
        ),
        "dataset_version": normalize_text(
            metadata.get("dataset_version")
        ),
        "chunk_schema_version": normalize_text(
            metadata.get("chunk_schema_version")
        ),
        "expert_review_version": normalize_text(
            metadata.get("expert_review_version")
        ),
        "status": normalize_text(
            metadata.get("status")
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Import MeetMind RAG v2.1 rules "
            "into an independent Chroma collection."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_FILE,
        help="RAG v2.1 JSONL source file.",
    )

    parser.add_argument(
        "--db-dir",
        type=Path,
        default=DEFAULT_DB_DIR,
        help="Chroma persistent database path.",
    )

    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION,
        help="Target Chroma collection name.",
    )

    parser.add_argument(
        "--embedding-model",
        default=DEFAULT_EMBEDDING_MODEL,
        help="Sentence Transformer model.",
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Delete only the specified target "
            "collection before import."
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    input_file = args.input.resolve()
    db_dir = args.db_dir.resolve()
    collection_name = args.collection.strip()
    embedding_model_name = (
        args.embedding_model.strip()
    )

    if collection_name in {
        "meeting_analyst_rules",
        "meeting_analyst_rules_v2_dedup_125",
    }:
        raise ImportValidationError(
            "Refusing to write protected "
            f"collection: {collection_name}"
        )

    chunks = load_chunks(input_file)

    ids = [
        normalize_text(
            item.get("chunk_id")
            or item.get("id")
        )
        for item in chunks
    ]

    documents = [
        build_embedding_text(item)
        for item in chunks
    ]

    metadatas = [
        make_chroma_metadata(item)
        for item in chunks
    ]

    print("Project root:", PROJECT_ROOT)
    print("Input file:", input_file)
    print("Vector DB:", db_dir)
    print("Collection:", collection_name)
    print(
        "Embedding model:",
        embedding_model_name,
    )
    print("Validated chunks:", len(chunks))

    print("\nLoading embedding model...")

    embedding_model = SentenceTransformer(
        embedding_model_name
    )

    print("Embedding model loaded.")
    print("\nGenerating embeddings...")

    embeddings = embedding_model.encode(
        documents,
        normalize_embeddings=True,
        show_progress_bar=True,
    ).tolist()

    if len(embeddings) != EXPECTED_COUNT:
        raise ImportValidationError(
            "Embedding count mismatch: "
            f"{len(embeddings)}"
        )

    print("Embeddings generated.")

    db_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    client = chromadb.PersistentClient(
        path=str(db_dir)
    )

    existing_names = {
        collection.name
        for collection in client.list_collections()
    }

    print(
        "\nCollections before import:",
        sorted(existing_names),
    )

    if args.reset:
        if collection_name in existing_names:
            client.delete_collection(
                collection_name
            )
            print(
                "Deleted target collection:",
                collection_name,
            )
        else:
            print(
                "Target collection did not exist:",
                collection_name,
            )

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={
            "description": (
                "MeetMind Meeting Analyst "
                "RAG v2.1"
            ),
            "dataset_version": (
                "meeting_analyst_rag_v2_1"
            ),
            "chunk_schema_version": (
                "rag-chunk-v2.1"
            ),
            "embedding_model": (
                embedding_model_name
            ),
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
            f"Collection count must be "
            f"{EXPECTED_COUNT}, got "
            f"{actual_count}"
        )

    final_names = {
        collection.name
        for collection in client.list_collections()
    }

    protected_collections = {
        "meeting_analyst_rules",
        "meeting_analyst_rules_v2_dedup_125",
    }

    missing_protected = (
        protected_collections
        - final_names
    )

    if missing_protected:
        print(
            "\nWarning: expected historical "
            "collections not found:",
            sorted(missing_protected),
        )

    print("\n============================")
    print("RAG v2.1 Import Success")
    print("============================")
    print("Imported:", len(ids))
    print("Collection count:", actual_count)
    print("Collection:", collection_name)
    print("DB path:", db_dir)
    print(
        "Collections after import:",
        sorted(final_names),
    )

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
        print(
            f"RAG v2.1 import failed: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1)