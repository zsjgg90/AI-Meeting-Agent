import json
from pathlib import Path

import torch
import chromadb

from tqdm import tqdm
from sentence_transformers import SentenceTransformer


# ============================================================
# MeetMind AI
# Gate B1 Phase5
# Retrieval Regression v3.4.1
#
# Fixed:
# source_chunk_id -> chunk_id mapping
# ============================================================


PROJECT_ROOT = Path(
    r"D:\codex_work\会议声纹识别"
)


QUERY_FILE = (
    PROJECT_ROOT
    /
    "data/rag/gate_b_v3_3/"
    "retrieval_eval_heldout_120_v1.jsonl"
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


TOP_K = 10



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



# ============================================================
# Main
# ============================================================


def main():


    print("="*70)

    print(
        "MeetMind AI"
    )

    print(
        "Gate B1 Phase5 Retrieval Regression v3.4.1"
    )

    print("="*70)



    # --------------------------------------------------------
    # Load queries
    # --------------------------------------------------------

    print(
        "\nLoading queries..."
    )


    queries = load_jsonl(
        QUERY_FILE
    )


    print(
        "Query count:",
        len(queries)
    )



    # --------------------------------------------------------
    # CUDA
    # --------------------------------------------------------

    print(
        "\nChecking CUDA"
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


    device = (

        "cuda"
        if cuda
        else
        "cpu"

    )


    if cuda:

        print(
            "GPU:",
            torch.cuda.get_device_name(0)
        )



    # --------------------------------------------------------
    # Model
    # --------------------------------------------------------

    print(
        "\nLoading BGE-M3"
    )


    model = SentenceTransformer(

        str(MODEL_PATH),

        device=device

    )


    print(
        "Embedding dimension:",
        model.get_embedding_dimension()
    )



    # --------------------------------------------------------
    # Chroma
    # --------------------------------------------------------

    print(
        "\nConnecting Chroma"
    )


    client = chromadb.PersistentClient(

        path=str(
            VECTOR_DB
        )

    )


    print(
        "Available collections:"
    )


    for c in client.list_collections():

        print(
            " -",
            c.name
        )



    collection = client.get_collection(

        COLLECTION_NAME

    )


    print(
        "Collection loaded:",
        COLLECTION_NAME
    )



    # --------------------------------------------------------
    # Build ID Mapping
    # --------------------------------------------------------

    print(
        "\nBuilding ID mapping..."
    )


    data = collection.get(

        include=[

            "metadatas"

        ]

    )


    source_to_chunk={}


    chunk_to_source={}



    for meta in data["metadatas"]:


        chunk_id = meta.get(
            "chunk_id"
        )


        source_id = meta.get(
            "source_chunk_id"
        )


        if chunk_id and source_id:


            source_to_chunk[source_id]=chunk_id


            chunk_to_source[chunk_id]=source_id



    print(
        "Source mapping:",
        len(source_to_chunk)
    )



    # --------------------------------------------------------
    # Retrieval
    # --------------------------------------------------------

    print(
        "\nRunning retrieval"
    )



    hit5=0

    hit10=0

    mrr=[]



    for item in tqdm(
        queries
    ):


        query_text=item[
            "query"
        ]


        gold_ids=item.get(

            "required_any_chunk_ids",

            []

        )



        # gold source ids
        gold_chunk_ids=[]


        for gid in gold_ids:


            mapped = source_to_chunk.get(

                gid

            )


            if mapped:

                gold_chunk_ids.append(
                    mapped
                )


            else:

                gold_chunk_ids.append(
                    gid
                )



        query_embedding=model.encode(

            query_text,

            normalize_embeddings=True

        )



        result=collection.query(

            query_embeddings=[

                query_embedding.tolist()

            ],

            n_results=TOP_K

        )



        retrieved_ids=result[
            "ids"
        ][0]



        found_rank=None



        for rank,cid in enumerate(

            retrieved_ids

        ):


            if cid in gold_chunk_ids:


                found_rank=rank

                break



        if found_rank is not None:


            if found_rank < 5:

                hit5 += 1



            if found_rank < 10:

                hit10 += 1



            mrr.append(

                1/(found_rank+1)

            )


        else:

            mrr.append(
                0
            )



    total=len(
        queries
    )



    report={


        "phase":

        "Gate B1 Phase5",



        "collection":

        COLLECTION_NAME,



        "model":

        "BAAI/bge-m3",



        "top_k":

        TOP_K,



        "query_count":

        total,



        "recall@5":

        hit5/total,



        "recall@10":

        hit10/total,



        "mrr@10":

        sum(mrr)/total,



        "hit_count@5":

        hit5,



        "hit_count@10":

        hit10

    }



    print()

    print("="*70)

    print(
        "Retrieval Report"
    )

    print("="*70)



    print(

        json.dumps(

            report,

            indent=2,

            ensure_ascii=False

        )

    )


    print()

    print(
        "PASS: Phase5 completed"
    )



if __name__=="__main__":

    main()