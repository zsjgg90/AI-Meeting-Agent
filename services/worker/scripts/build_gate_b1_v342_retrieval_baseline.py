import json
import hashlib
from pathlib import Path

import torch
import chromadb

from tqdm import tqdm
from sentence_transformers import SentenceTransformer


# ============================================================
# MeetMind AI
# Gate B1 Phase6.2
# BGE-M3 Dense Retrieval Builder v3.4.2
# ============================================================


PROJECT_ROOT = Path(
    r"D:\codex_work\会议声纹识别"
)


CORPUS_FILE = (
    PROJECT_ROOT
    /
    "data/rag/gate_b_v3_4_2/"
    "meeting_analyst_rag_v3_4_2_enriched.jsonl"
)


VECTOR_DB = (
    PROJECT_ROOT
    /
    "data/vector_db/"
    "gate_b1_v34_2"
)


MODEL_PATH = Path(
    r"D:\model_cache\bge-m3"
)


COLLECTION_NAME = (
    "meeting_analyst_rules_gate_b_v3_4_2_bge_m3_dense_v1"
)


BATCH_SIZE = 16



# ============================================================
# Utils
# ============================================================


def sha256_file(path):

    h = hashlib.sha256()

    with open(
        path,
        "rb"
    ) as f:

        for chunk in iter(
            lambda:f.read(1024*1024),
            b""
        ):
            h.update(chunk)


    return h.hexdigest()



def load_jsonl(path):

    rows=[]

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        for line in f:

            if line.strip():

                rows.append(
                    json.loads(line)
                )

    return rows



def build_embedding_text(row):


    parts=[]


    def add(value):

        if not value:
            return


        if isinstance(value,list):

            for x in value:

                if x:

                    parts.append(
                        str(x)
                    )

        else:

            parts.append(
                str(value)
            )



    add(
        row.get("title")
    )


    add(
        row.get("definition")
    )


    add(
        row.get("decision_rule")
    )


    add(
        row.get("positive_examples")
    )


    add(
        row.get("negative_examples")
    )


    add(
        row.get("keywords")
    )


    # Phase6 NEW
    add(
        row.get("query_patterns")
    )


    return "\n".join(parts)



# ============================================================
# Main
# ============================================================


def main():


    print("="*76)

    print(
        "MeetMind AI"
    )

    print(
        "Gate B1 Phase6.2"
    )

    print(
        "BGE-M3 Dense Retrieval Builder v3.4.2"
    )

    print("="*76)



    # --------------------------------------------------------
    # Paths
    # --------------------------------------------------------

    print("\n[1/9] Checking paths...")


    print(
        "Corpus:"
    )

    print(
        CORPUS_FILE
    )


    print(
        "Vector DB:"
    )

    print(
        VECTOR_DB
    )


    print(
        "Model:"
    )

    print(
        MODEL_PATH
    )



    if not CORPUS_FILE.exists():

        raise FileNotFoundError(
            CORPUS_FILE
        )


    if not MODEL_PATH.exists():

        raise FileNotFoundError(
            MODEL_PATH
        )



    VECTOR_DB.mkdir(
        parents=True,
        exist_ok=True
    )



    # --------------------------------------------------------
    # Corpus
    # --------------------------------------------------------

    print(
        "\n[2/9] Loading corpus..."
    )


    rows=load_jsonl(
        CORPUS_FILE
    )


    print(
        "Corpus rows:",
        len(rows)
    )



    for i,row in enumerate(rows):


        required=[
            "chunk_id",
            "title",
            "definition"
        ]


        for f in required:

            if f not in row:

                raise ValueError(
                    f"Missing {f} at row {i}"
                )



    print(
        "Corpus validation: PASS"
    )



    # --------------------------------------------------------
    # Text
    # --------------------------------------------------------

    print(
        "\n[3/9] Building embedding texts..."
    )


    texts=[]


    for row in rows:

        texts.append(
            build_embedding_text(row)
        )



    print(
        "Embedding text count:",
        len(texts)
    )



    # --------------------------------------------------------
    # CUDA
    # --------------------------------------------------------

    print(
        "\n[4/9] Checking CUDA..."
    )


    print(
        "Torch:",
        torch.__version__
    )


    cuda=torch.cuda.is_available()


    print(
        "CUDA:",
        cuda
    )


    device="cuda" if cuda else "cpu"


    if cuda:

        print(
            "GPU:",
            torch.cuda.get_device_name(0)
        )



    # --------------------------------------------------------
    # Model
    # --------------------------------------------------------

    print(
        "\n[5/9] Loading BGE-M3..."
    )


    model=SentenceTransformer(

        str(MODEL_PATH),

        device=device

    )


    dim=model.get_embedding_dimension()


    print(
        "Dimension:",
        dim
    )


    print(
        "Model loaded PASS"
    )



    # --------------------------------------------------------
    # Encode
    # --------------------------------------------------------

    print(
        "\n[6/9] Encoding..."
    )


    embeddings=model.encode(

        texts,

        batch_size=BATCH_SIZE,

        normalize_embeddings=True,

        show_progress_bar=True

    )


    print(
        "Embedding shape:",
        embeddings.shape
    )



    # --------------------------------------------------------
    # Chroma
    # --------------------------------------------------------

    print(
        "\n[7/9] Preparing Chroma..."
    )


    client=chromadb.PersistentClient(

        path=str(
            VECTOR_DB
        )

    )



    try:

        client.delete_collection(
            COLLECTION_NAME
        )

    except Exception:

        pass



    collection=client.create_collection(

        name=COLLECTION_NAME,

        metadata={
            "hnsw:space":"cosine",
            "model":"BAAI/bge-m3",
            "version":"v3_4_2"
        }

    )



    print(
        "Collection:",
        COLLECTION_NAME
    )



    # --------------------------------------------------------
    # Insert
    # --------------------------------------------------------

    print(
        "\n[8/9] Inserting vectors..."
    )


    ids=[]

    metadatas=[]



    for row in rows:

        ids.append(
            row["chunk_id"]
        )


        metadatas.append(

            {
                "chunk_id":
                    row.get("chunk_id"),

                "source_chunk_id":
                    row.get("source_chunk_id",""),

                "dimension":
                    row.get("dimension",""),

                "schema_version":
                    row.get("schema_version",""),

                "chunk_type":
                    row.get("chunk_type","")

            }

        )



    collection.add(

        ids=ids,

        embeddings=[
            x.tolist()
            for x in embeddings
        ],

        documents=texts,

        metadatas=metadatas

    )


    print(
        "Inserted:",
        len(ids)
    )



    # --------------------------------------------------------
    # Verify
    # --------------------------------------------------------

    print(
        "\n[9/9] Verification..."
    )


    count=collection.count()


    print(
        "Collection count:",
        count
    )



    if count != len(rows):

        raise RuntimeError(
            "Count mismatch"
        )


    print(
        "Collection validation PASS"
    )



    print("\n")

    print("="*76)

    print(
        "GATE B1 PHASE6.2 BUILD RESULT"
    )

    print("="*76)


    print(
        "Status: PASS"
    )

    print(
        "Corpus:",
        len(rows)
    )

    print(
        "Inserted:",
        count
    )

    print(
        "Embedding: BAAI/bge-m3"
    )

    print(
        "Collection:",
        COLLECTION_NAME
    )

    print("="*76)



if __name__=="__main__":

    main()