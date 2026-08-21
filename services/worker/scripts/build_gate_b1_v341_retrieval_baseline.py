import json
import shutil
from pathlib import Path
from datetime import datetime, timezone

import torch
import chromadb

from tqdm import tqdm
from sentence_transformers import SentenceTransformer


# ============================================================
# MeetMind AI
# Gate B1 Phase5
# BGE-M3 Dense Retrieval Builder v3.4.1
#
# Rule Pack Schema Compatible
# ============================================================


PROJECT_ROOT = Path(
    r"D:\codex_work\会议声纹识别"
)


CORPUS_FILE = (
    PROJECT_ROOT
    /
    "data/rag/gate_b_v3_4/"
    "meeting_analyst_rag_v3_4_1_enriched.jsonl"
)


VECTOR_DB = (
    PROJECT_ROOT
    /
    "data/vector_db/gate_b1_v34_1"
)


MODEL_PATH = Path(
    r"D:\model_cache\bge-m3"
)


COLLECTION_NAME = (
    "meeting_analyst_rules_gate_b_v3_4_1_bge_m3_dense_v1"
)


BATCH_SIZE = 16



# ============================================================
# Utils
# ============================================================


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

    """
    Rule Pack v3.4 embedding contract

    title
    definition
    decision_rule
    positive_examples
    negative_examples
    keywords
    """

    parts=[]


    fields=[

        row.get(
            "title",
            ""
        ),

        row.get(
            "definition",
            ""
        )

    ]


    parts.extend(fields)



    for key in [

        "decision_rule",

        "positive_examples",

        "negative_examples",

        "keywords"

    ]:


        value=row.get(
            key,
            []
        )


        if isinstance(
            value,
            list
        ):

            parts.extend(
                value
            )


        elif value:

            parts.append(
                value
            )



    return "\n".join(

        [
            str(x)
            for x in parts
            if x
        ]

    )



# ============================================================
# Main
# ============================================================


def main():


    print("="*76)

    print(
        "MeetMind AI"
    )

    print(
        "Gate B1 Phase5"
    )

    print(
        "BGE-M3 Dense Retrieval Builder v3.4.1"
    )

    print("="*76)



    # --------------------------------------------------------
    # 1 Paths
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



    # --------------------------------------------------------
    # 2 Corpus
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



    for r in rows:


        if not r.get(
            "chunk_id"
        ):

            raise ValueError(
                "missing chunk_id"
            )


        if not r.get(
            "title"
        ):

            raise ValueError(
                "missing title"
            )



    print(
        "Corpus validation: PASS"
    )



    # --------------------------------------------------------
    # 3 Text
    # --------------------------------------------------------

    print(
        "\n[3/9] Building embedding texts..."
    )


    texts=[]


    for r in rows:

        texts.append(
            build_embedding_text(r)
        )


    print(
        "Embedding text count:",
        len(texts)
    )



    # --------------------------------------------------------
    # 4 CUDA
    # --------------------------------------------------------

    print(
        "\n[4/9] Checking CUDA..."
    )


    print(
        "Torch:",
        torch.__version__
    )


    print(
        "CUDA:",
        torch.cuda.is_available()
    )


    device=(

        "cuda"
        if torch.cuda.is_available()
        else "cpu"

    )


    if device=="cuda":

        print(
            "GPU:",
            torch.cuda.get_device_name(0)
        )



    # --------------------------------------------------------
    # 5 Model
    # --------------------------------------------------------

    print(
        "\n[5/9] Loading BGE-M3..."
    )


    model=SentenceTransformer(

        str(MODEL_PATH),

        device=device

    )


    print(
        "Dimension:",
        model.get_embedding_dimension()
    )


    print(
        "Model loaded PASS"
    )



    # --------------------------------------------------------
    # 6 Embedding
    # --------------------------------------------------------

    print(
        "\n[6/9] Encoding..."
    )


    embeddings=[]


    for i in tqdm(

        range(
            0,
            len(texts),
            BATCH_SIZE
        )

    ):


        batch=texts[
            i:i+BATCH_SIZE
        ]


        emb=model.encode(

            batch,

            normalize_embeddings=True

        )


        embeddings.extend(

            emb.tolist()

        )



    print(

        "Embedding shape:",

        (
            len(embeddings),
            len(embeddings[0])
        )

    )



    # --------------------------------------------------------
    # 7 Chroma
    # --------------------------------------------------------

    print(
        "\n[7/9] Preparing Chroma..."
    )


    if VECTOR_DB.exists():

        shutil.rmtree(
            VECTOR_DB
        )


    VECTOR_DB.mkdir(

        parents=True,

        exist_ok=True

    )



    client=chromadb.PersistentClient(

        path=str(
            VECTOR_DB
        )

    )


    collection=client.create_collection(

        name=COLLECTION_NAME,

        metadata={

            "hnsw:space":
            "cosine"

        }

    )



    print(
        "Collection:",
        COLLECTION_NAME
    )



    # --------------------------------------------------------
    # 8 Insert
    # --------------------------------------------------------

    print(
        "\n[8/9] Inserting vectors..."
    )


    ids=[]

    metadatas=[]

    documents=[]



    for row,text in zip(

        rows,

        texts

    ):


        ids.append(

            row["chunk_id"]

        )


        metadatas.append(

            {

                "chunk_id":
                row.get(
                    "chunk_id",
                    ""
                ),


                "source_chunk_id":
                row.get(
                    "source_chunk_id",
                    ""
                ),


                "dimension":
                row.get(
                    "dimension",
                    ""
                ),


                "schema_version":
                row.get(
                    "schema_version",
                    ""
                ),


                "chunk_type":
                row.get(
                    "chunk_type",
                    ""
                )

            }

        )


        documents.append(
            text
        )



    collection.add(

        ids=ids,

        embeddings=embeddings,

        documents=documents,

        metadatas=metadatas

    )


    print(
        "Inserted:",
        len(ids)
    )



    # --------------------------------------------------------
    # 9 Verify
    # --------------------------------------------------------

    print(
        "\n[9/9] Verification..."
    )


    count=collection.count()


    print(
        "Collection count:",
        count
    )



    sample=collection.get(

        limit=3,

        include=[

            "metadatas"

        ]

    )


    print(
        "\nMetadata sample:"
    )


    for m in sample["metadatas"]:

        print(
            m
        )



    assert (

        "source_chunk_id"

        in

        sample["metadatas"][0]

    )



    print(
        "\nCollection validation PASS"
    )



    print("\n")
    print("="*76)

    print(
        "GATE B1 PHASE5 BUILD RESULT"
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
        "Collection:",
        COLLECTION_NAME
    )


    print("="*76)



if __name__=="__main__":

    main()