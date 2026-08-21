import hashlib
import json
import os
import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import chromadb
import numpy as np
import torch
from sentence_transformers import SentenceTransformer


# ============================================================
# Gate B1 Phase 3
# BGE-M3 Dense Retrieval Baseline
#
# FROZEN CONFIGURATION
# ============================================================

ROOT = Path.cwd()

# ------------------------------------------------------------
# Corpus
# ------------------------------------------------------------

CORPUS_PATH = (
    ROOT
    / "data"
    / "rag"
    / "gate_b_v3_3"
    / "meeting_analyst_rag_v3_3_0_candidate.jsonl"
)

CORPUS_VERSION = "meeting_analyst_rag_v3_3_0"
CORPUS_STATUS = "FROZEN_CANDIDATE"

EXPECTED_CORPUS_COUNT = 515


# ------------------------------------------------------------
# BGE-M3
#
# Model identity and physical path are deliberately separated.
# ------------------------------------------------------------

MODEL_ID = "BAAI/bge-m3"

MODEL_LOCAL_PATH = Path(
    r"D:\model_cache\bge-m3"
)

MODEL_SOURCE = "ModelScope"

MODEL_WEIGHTS_PATH = (
    MODEL_LOCAL_PATH
    / "pytorch_model.bin"
)

EXPECTED_EMBEDDING_DIMENSION = 1024


# ------------------------------------------------------------
# Chroma
# ------------------------------------------------------------

DB_PATH = (
    ROOT
    / "data"
    / "vector_db"
    / "gate_b1_v3_3"
)

COLLECTION_NAME = (
    "meeting_analyst_rules_gate_b_v3_3_bge_m3_dense_v1"
)

DISTANCE_METRIC = "cosine"


# ------------------------------------------------------------
# Phase 3 output
# ------------------------------------------------------------

OUTPUT_DIR = (
    ROOT
    / "data"
    / "rag"
    / "gate_b_v3_3"
    / "phase3"
)

MANIFEST_PATH = (
    OUTPUT_DIR
    / "collection_manifest.json"
)


# ------------------------------------------------------------
# Frozen retrieval baseline
# ------------------------------------------------------------

EMBEDDING_TEXT_TEMPLATE = "{title}\\n{content}"

NORMALIZE_EMBEDDINGS = True

TOP_K = 10

RERANK_ENABLED = False

HYBRID_ENABLED = False

METADATA_FILTER_ENABLED = False

EMBEDDING_BATCH_SIZE = 16

CHROMA_INSERT_BATCH_SIZE = 100


# ============================================================
# Utility
# ============================================================

def package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "unknown"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            block = f.read(1024 * 1024)

            if not block:
                break

            digest.update(block)

    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    rows = []

    with path.open(
        "r",
        encoding="utf-8",
    ) as f:

        for line_number, raw_line in enumerate(
            f,
            start=1,
        ):

            line = raw_line.strip()

            if not line:
                continue

            try:
                row = json.loads(line)

            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Invalid JSONL at line {line_number}: {exc}"
                ) from exc

            if not isinstance(row, dict):
                raise RuntimeError(
                    f"Line {line_number} is not a JSON object."
                )

            rows.append(row)

    return rows


def build_embedding_text(row: dict) -> str:
    title = str(
        row.get("title") or ""
    ).strip()

    content = str(
        row.get("content") or ""
    ).strip()

    chunk_id = row.get(
        "chunk_id",
        "<unknown>",
    )

    if not title:
        raise RuntimeError(
            f"Empty title: {chunk_id}"
        )

    if not content:
        raise RuntimeError(
            f"Empty content: {chunk_id}"
        )

    # ========================================================
    # FROZEN EMBEDDING CONTRACT
    #
    # title
    # +
    # newline
    # +
    # content
    #
    # Metadata is NOT embedded.
    # ========================================================

    return f"{title}\n{content}"


def flatten_metadata(row: dict) -> dict:
    source_metadata = dict(
        row.get("metadata") or {}
    )

    source_metadata["chunk_id"] = (
        row["chunk_id"]
    )

    source_metadata["title"] = (
        row["title"]
    )

    source_metadata["source_id"] = (
        row["id"]
    )

    metadata = {}

    # Chroma baseline only accepts scalar metadata.
    for key, value in source_metadata.items():

        if value is None:
            continue

        if isinstance(
            value,
            (str, int, float, bool),
        ):
            metadata[str(key)] = value

    return metadata


def get_collection_names(
    client: chromadb.PersistentClient,
) -> list[str]:

    names = []

    for item in client.list_collections():

        if isinstance(item, str):
            names.append(item)

        elif hasattr(item, "name"):
            names.append(item.name)

        else:
            names.append(str(item))

    return names


def create_cosine_collection(
    client: chromadb.PersistentClient,
):
    """
    Chroma 1.x prefers configuration={
        "hnsw": {"space": "cosine"}
    }

    Older-compatible path uses:
        metadata={"hnsw:space": "cosine"}

    This function supports both without changing
    the frozen retrieval semantics.
    """

    try:
        collection = client.create_collection(
            name=COLLECTION_NAME,
            configuration={
                "hnsw": {
                    "space": DISTANCE_METRIC,
                }
            },
        )

        print(
            "Chroma configuration mode: "
            "configuration.hnsw.space"
        )

        return collection

    except (TypeError, ValueError) as exc:

        print(
            "[INFO] Current Chroma rejected "
            "configuration API."
        )

        print(
            f"[INFO] Reason: {exc}"
        )

        print(
            "[INFO] Trying compatible "
            "metadata hnsw:space configuration."
        )

    return client.create_collection(
        name=COLLECTION_NAME,
        metadata={
            "hnsw:space":
                DISTANCE_METRIC,
        },
    )


def validate_embedding_norms(
    embeddings: np.ndarray,
):
    if embeddings.ndim != 2:
        raise RuntimeError(
            f"Unexpected embedding ndim: "
            f"{embeddings.ndim}"
        )

    norms = np.linalg.norm(
        embeddings,
        axis=1,
    )

    max_deviation = float(
        np.max(
            np.abs(norms - 1.0)
        )
    )

    print(
        f"Max normalized-vector deviation: "
        f"{max_deviation:.8f}"
    )

    # Small numerical tolerance.
    if max_deviation > 1e-3:
        raise RuntimeError(
            "Embeddings are not properly normalized."
        )


# ============================================================
# Main
# ============================================================

def main():

    print("=" * 76)
    print("MeetMind AI")
    print("Gate B1 Phase 3")
    print("BGE-M3 Dense Retrieval Baseline Builder")
    print("=" * 76)

    # ========================================================
    # Step 1
    # Paths
    # ========================================================

    print("\n[1/9] Checking paths...")

    if not CORPUS_PATH.exists():
        raise FileNotFoundError(
            f"Corpus not found:\n"
            f"{CORPUS_PATH}"
        )

    if not MODEL_LOCAL_PATH.exists():
        raise FileNotFoundError(
            f"BGE-M3 local directory "
            f"not found:\n"
            f"{MODEL_LOCAL_PATH}"
        )

    required_model_files = [
        MODEL_LOCAL_PATH / "config.json",
        MODEL_LOCAL_PATH / "modules.json",
        MODEL_LOCAL_PATH
        / "sentence_bert_config.json",
        MODEL_LOCAL_PATH
        / "tokenizer.json",
        MODEL_LOCAL_PATH
        / "tokenizer_config.json",
        MODEL_WEIGHTS_PATH,
    ]

    missing_model_files = [
        str(path)
        for path in required_model_files
        if not path.exists()
    ]

    if missing_model_files:
        raise RuntimeError(
            "BGE-M3 local snapshot "
            "is incomplete.\nMissing:\n"
            + "\n".join(
                missing_model_files
            )
        )

    DB_PATH.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(f"Corpus       : {CORPUS_PATH}")
    print(f"Vector DB    : {DB_PATH}")
    print(f"Phase Output : {OUTPUT_DIR}")
    print(f"Model ID     : {MODEL_ID}")
    print(f"Model Source : {MODEL_SOURCE}")
    print(f"Local Model  : {MODEL_LOCAL_PATH}")


    # ========================================================
    # Step 2
    # Corpus validation
    # ========================================================

    print(
        "\n[2/9] Loading and validating corpus..."
    )

    rows = load_jsonl(
        CORPUS_PATH
    )

    print(
        f"Corpus rows: {len(rows)}"
    )

    if len(rows) != EXPECTED_CORPUS_COUNT:
        raise RuntimeError(
            "Corpus count mismatch. "
            f"Expected={EXPECTED_CORPUS_COUNT}, "
            f"Actual={len(rows)}"
        )

    ids = []
    chunk_ids = []
    contents = []

    required_fields = {
        "id",
        "chunk_id",
        "title",
        "content",
        "metadata",
    }

    for row_number, row in enumerate(
        rows,
        start=1,
    ):

        missing = (
            required_fields
            - set(row.keys())
        )

        if missing:
            raise RuntimeError(
                f"Corpus row {row_number} "
                f"missing fields: "
                f"{sorted(missing)}"
            )

        if not isinstance(
            row["metadata"],
            dict,
        ):
            raise RuntimeError(
                f"Corpus row {row_number}: "
                f"metadata must be object."
            )

        row_id = str(
            row["id"]
        )

        chunk_id = str(
            row["chunk_id"]
        )

        if row_id != chunk_id:
            raise RuntimeError(
                f"id != chunk_id: "
                f"{row_id} / {chunk_id}"
            )

        ids.append(
            row_id
        )

        chunk_ids.append(
            chunk_id
        )

        contents.append(
            str(row["content"])
        )

    if len(set(ids)) != len(ids):
        raise RuntimeError(
            "Duplicate id detected."
        )

    if len(set(chunk_ids)) != len(chunk_ids):
        raise RuntimeError(
            "Duplicate chunk_id detected."
        )

    if len(set(contents)) != len(contents):
        raise RuntimeError(
            "Duplicate exact content detected."
        )

    corpus_versions = {
        row["metadata"].get(
            "corpus_version"
        )
        for row in rows
    }

    if corpus_versions != {
        CORPUS_VERSION
    }:
        raise RuntimeError(
            "Unexpected corpus_version. "
            f"Actual={corpus_versions}"
        )

    corpus_statuses = {
        row["metadata"].get(
            "corpus_status"
        )
        for row in rows
    }

    if corpus_statuses != {
        CORPUS_STATUS
    }:
        raise RuntimeError(
            "Unexpected corpus_status. "
            f"Actual={corpus_statuses}"
        )

    print(
        "Corpus validation: PASS"
    )


    # ========================================================
    # Step 3
    # Embedding text
    # ========================================================

    print(
        "\n[3/9] Building embedding texts..."
    )

    texts = [
        build_embedding_text(row)
        for row in rows
    ]

    if len(texts) != EXPECTED_CORPUS_COUNT:
        raise RuntimeError(
            "Embedding text count mismatch."
        )

    print(
        'Embedding contract: '
        'title + "\\n" + content'
    )

    print(
        f"Embedding text count: "
        f"{len(texts)}"
    )


    # ========================================================
    # Step 4
    # GPU
    # ========================================================

    print(
        "\n[4/9] Checking CUDA baseline..."
    )

    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA unavailable.\n"
            "Gate B1 frozen baseline "
            "requires CUDA."
        )

    device = "cuda"

    gpu_name = (
        torch.cuda.get_device_name(0)
    )

    print(
        f"Python        : "
        f"{platform.python_version()}"
    )

    print(
        f"Torch         : "
        f"{torch.__version__}"
    )

    print(
        f"CUDA Runtime  : "
        f"{torch.version.cuda}"
    )

    print(
        f"GPU           : "
        f"{gpu_name}"
    )


    # ========================================================
    # Step 5
    # Load local BGE-M3
    # ========================================================

    print(
        "\n[5/9] Loading local BGE-M3..."
    )

    # Prevent accidental network fallback.
    os.environ[
        "HF_HUB_OFFLINE"
    ] = "1"

    os.environ[
        "TRANSFORMERS_OFFLINE"
    ] = "1"

    model = SentenceTransformer(
        str(MODEL_LOCAL_PATH),
        device=device,
    )

    model_dimension = (
        model
        .get_sentence_embedding_dimension()
    )

    print(
        f"Model loaded: {MODEL_ID}"
    )

    print(
        f"Local path  : "
        f"{MODEL_LOCAL_PATH}"
    )

    print(
        f"Dimension   : "
        f"{model_dimension}"
    )

    if (
        model_dimension
        != EXPECTED_EMBEDDING_DIMENSION
    ):
        raise RuntimeError(
            "Unexpected BGE-M3 dimension. "
            f"Expected="
            f"{EXPECTED_EMBEDDING_DIMENSION}, "
            f"Actual={model_dimension}"
        )

    print(
        "Local model validation: PASS"
    )


    # ========================================================
    # Step 6
    # Encode corpus
    # ========================================================

    print(
        "\n[6/9] Encoding corpus..."
    )

    embeddings = model.encode(
        texts,
        batch_size=EMBEDDING_BATCH_SIZE,
        show_progress_bar=True,
        normalize_embeddings=
            NORMALIZE_EMBEDDINGS,
        convert_to_numpy=True,
    )

    embeddings = np.asarray(
        embeddings,
        dtype=np.float32,
    )

    print(
        f"Embedding shape: "
        f"{embeddings.shape}"
    )

    if (
        embeddings.shape
        != (
            EXPECTED_CORPUS_COUNT,
            EXPECTED_EMBEDDING_DIMENSION,
        )
    ):
        raise RuntimeError(
            "Embedding shape mismatch. "
            f"Expected="
            f"("
            f"{EXPECTED_CORPUS_COUNT}, "
            f"{EXPECTED_EMBEDDING_DIMENSION}"
            f"), "
            f"Actual="
            f"{embeddings.shape}"
        )

    if not np.isfinite(
        embeddings
    ).all():
        raise RuntimeError(
            "Embedding matrix contains "
            "NaN or Inf."
        )

    validate_embedding_norms(
        embeddings
    )

    print(
        "Embedding validation: PASS"
    )


    # ========================================================
    # Step 7
    # Chroma
    # ========================================================

    print(
        "\n[7/9] Preparing Chroma collection..."
    )

    client = (
        chromadb.PersistentClient(
            path=str(DB_PATH)
        )
    )

    existing_names = (
        get_collection_names(
            client
        )
    )

    if (
        COLLECTION_NAME
        in existing_names
    ):
        raise RuntimeError(
            "\nFrozen collection "
            "already exists:\n"
            f"{COLLECTION_NAME}\n\n"
            "This script will NOT "
            "overwrite an existing baseline."
        )

    collection = None
    collection_created = False

    try:

        collection = (
            create_cosine_collection(
                client
            )
        )

        collection_created = True

        print(
            f"Collection created: "
            f"{COLLECTION_NAME}"
        )


        # ====================================================
        # Step 8
        # Insert
        # ====================================================

        print(
            "\n[8/9] Inserting 515 vectors..."
        )

        for start in range(
            0,
            EXPECTED_CORPUS_COUNT,
            CHROMA_INSERT_BATCH_SIZE,
        ):

            end = min(
                start
                + CHROMA_INSERT_BATCH_SIZE,
                EXPECTED_CORPUS_COUNT,
            )

            batch_rows = (
                rows[start:end]
            )

            collection.add(
                ids=[
                    row["chunk_id"]
                    for row
                    in batch_rows
                ],

                documents=
                    texts[start:end],

                embeddings=(
                    embeddings[
                        start:end
                    ]
                    .tolist()
                ),

                metadatas=[
                    flatten_metadata(row)
                    for row
                    in batch_rows
                ],
            )

            print(
                f"Inserted: "
                f"{end}/"
                f"{EXPECTED_CORPUS_COUNT}"
            )


        # ====================================================
        # Step 9
        # Verify
        # ====================================================

        print(
            "\n[9/9] Verifying collection..."
        )

        final_count = (
            collection.count()
        )

        print(
            f"Final collection count: "
            f"{final_count}"
        )

        if (
            final_count
            != EXPECTED_CORPUS_COUNT
        ):
            raise RuntimeError(
                "Collection count mismatch. "
                f"Expected="
                f"{EXPECTED_CORPUS_COUNT}, "
                f"Actual={final_count}"
            )

        # Basic readback validation.
        sample_ids = (
            chunk_ids[:3]
        )

        readback = (
            collection.get(
                ids=sample_ids,
                include=[
                    "documents",
                    "metadatas",
                ],
            )
        )

        returned_ids = set(
            readback.get(
                "ids",
                [],
            )
        )

        if returned_ids != set(
            sample_ids
        ):
            raise RuntimeError(
                "Chroma readback validation failed."
            )

        print(
            "Chroma readback validation: PASS"
        )

    except Exception:

        # Only remove a collection that THIS run created.
        # Existing frozen collections are never touched.
        if collection_created:

            print(
                "\n[ERROR] Build failed "
                "after collection creation."
            )

            print(
                "[INFO] Removing partial "
                "collection created by "
                "this failed run..."
            )

            try:
                client.delete_collection(
                    COLLECTION_NAME
                )

                print(
                    "[INFO] Partial "
                    "collection removed."
                )

            except Exception as cleanup_exc:

                print(
                    "[WARNING] Failed "
                    "to remove partial "
                    f"collection: "
                    f"{cleanup_exc}"
                )

        raise


    # ========================================================
    # Reproducibility metadata
    # ========================================================

    print(
        "\nCalculating frozen baseline fingerprints..."
    )

    corpus_sha256 = (
        sha256_file(
            CORPUS_PATH
        )
    )

    print(
        "Corpus SHA256 complete."
    )

    # This is a ~2.27 GB file.
    # Hashing may take some time but is intentional:
    # it freezes the actual model weights used.
    weights_sha256 = (
        sha256_file(
            MODEL_WEIGHTS_PATH
        )
    )

    print(
        "Model weights SHA256 complete."
    )

    model_revision = None

    try:
        auto_model = (
            model[0].auto_model
        )

        model_revision = getattr(
            auto_model.config,
            "_commit_hash",
            None,
        )

    except Exception:
        pass


    # ========================================================
    # Manifest
    # ========================================================

    manifest = {

        "phase":
            "Gate B1 Phase 3",

        "baseline_version":
            "gate-b1-bge-m3-dense-v1",

        "status":
            "BUILT",

        # -----------------------------------------------
        # Corpus
        # -----------------------------------------------

        "corpus_version":
            CORPUS_VERSION,

        "corpus_status":
            CORPUS_STATUS,

        "corpus_count":
            EXPECTED_CORPUS_COUNT,

        "corpus_sha256":
            corpus_sha256,

        # -----------------------------------------------
        # Model
        # -----------------------------------------------

        "embedding_model":
            MODEL_ID,

        "embedding_source":
            MODEL_SOURCE,

        "embedding_local_path":
            str(MODEL_LOCAL_PATH),

        "embedding_revision":
            model_revision,

        "model_weights_file":
            MODEL_WEIGHTS_PATH.name,

        "model_weights_bytes":
            MODEL_WEIGHTS_PATH.stat().st_size,

        "model_weights_sha256":
            weights_sha256,

        "embedding_dimension":
            EXPECTED_EMBEDDING_DIMENSION,

        "embedding_text_template":
            EMBEDDING_TEXT_TEMPLATE,

        "normalize_embeddings":
            NORMALIZE_EMBEDDINGS,

        # -----------------------------------------------
        # Retrieval
        # -----------------------------------------------

        "retrieval_type":
            "dense",

        "distance":
            DISTANCE_METRIC,

        "top_k":
            TOP_K,

        "rerank":
            RERANK_ENABLED,

        "hybrid":
            HYBRID_ENABLED,

        "metadata_filter":
            METADATA_FILTER_ENABLED,

        # -----------------------------------------------
        # Chroma
        # -----------------------------------------------

        "collection_name":
            COLLECTION_NAME,

        "collection_count":
            final_count,

        "vector_db_path":
            str(DB_PATH),

        # -----------------------------------------------
        # Runtime
        # -----------------------------------------------

        "device":
            device,

        "gpu":
            gpu_name,

        "python_version":
            platform.python_version(),

        "python_executable":
            sys.executable,

        "torch_version":
            torch.__version__,

        "torch_cuda_runtime":
            torch.version.cuda,

        "chromadb_version":
            package_version(
                "chromadb"
            ),

        "sentence_transformers_version":
            package_version(
                "sentence-transformers"
            ),

        "numpy_version":
            package_version(
                "numpy"
            ),

        "embedding_batch_size":
            EMBEDDING_BATCH_SIZE,

        "chroma_insert_batch_size":
            CHROMA_INSERT_BATCH_SIZE,
    }

    MANIFEST_PATH.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


    # ========================================================
    # Final
    # ========================================================

    print(
        "\n"
        + "=" * 76
    )

    print(
        "GATE B1 PHASE 3 "
        "- BUILD RESULT"
    )

    print(
        "=" * 76
    )

    print(
        "Status      : PASS"
    )

    print(
        f"Corpus      : "
        f"{EXPECTED_CORPUS_COUNT}"
    )

    print(
        f"Inserted    : "
        f"{final_count}"
    )

    print(
        f"Embedding   : "
        f"{MODEL_ID}"
    )

    print(
        f"Source      : "
        f"{MODEL_SOURCE}"
    )

    print(
        f"Local Model : "
        f"{MODEL_LOCAL_PATH}"
    )

    print(
        f"Dimension   : "
        f"{EXPECTED_EMBEDDING_DIMENSION}"
    )

    print(
        f"Normalize   : "
        f"{NORMALIZE_EMBEDDINGS}"
    )

    print(
        f"Distance    : "
        f"{DISTANCE_METRIC}"
    )

    print(
        "Retrieval   : Dense"
    )

    print(
        f"Top-K       : "
        f"{TOP_K}"
    )

    print(
        "Rerank      : OFF"
    )

    print(
        "Hybrid      : OFF"
    )

    print(
        "MetadataFilter: OFF"
    )

    print(
        f"GPU         : "
        f"{gpu_name}"
    )

    print(
        f"Collection  : "
        f"{COLLECTION_NAME}"
    )

    print(
        f"Manifest    : "
        f"{MANIFEST_PATH}"
    )

    print(
        "=" * 76
    )


if __name__ == "__main__":
    main()