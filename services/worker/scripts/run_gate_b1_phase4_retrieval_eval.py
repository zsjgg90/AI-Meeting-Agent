import json
import os
from pathlib import Path

import chromadb
import numpy as np
from sentence_transformers import SentenceTransformer


ROOT = Path.cwd()


QUERY_FILE = (
    ROOT
    / "data"
    / "rag"
    / "gate_b_v3_3"
    / "retrieval_eval_heldout_120_v1.jsonl"
)


MODEL_PATH = Path(
    r"D:\model_cache\bge-m3"
)


DB_PATH = (
    ROOT
    / "data"
    / "vector_db"
    / "gate_b1_v3_3"
)


COLLECTION_NAME = (
    "meeting_analyst_rules_gate_b_v3_3_bge_m3_dense_v1"
)


OUTPUT_DIR = (
    ROOT
    / "data"
    / "rag"
    / "gate_b_v3_3"
    / "phase4"
)


TOP_K = 10


def fix_mojibake(text):

    try:
        if "?" in text:
            return text

        return text.encode(
            "latin1"
        ).decode(
            "utf-8"
        )

    except Exception:
        return text



def load_queries():

    rows=[]

    with open(
        QUERY_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        for line in f:

            if not line.strip():
                continue

            item=json.loads(line)

            item["query"]=fix_mojibake(
                item["query"]
            )

            rows.append(item)

    return rows



def recall_hit(
    retrieved,
    required
):

    ids=set(required)

    for item in retrieved:

        if item["chunk_id"] in ids:
            return True

    return False



def calculate_mrr(
    retrieved,
    required
):

    ids=set(required)

    for rank,item in enumerate(
        retrieved,
        start=1
    ):

        if item["chunk_id"] in ids:
            return 1/rank

    return 0



def main():

    print("="*70)
    print(
        "Gate B1 Phase4 Retrieval Regression"
    )
    print("="*70)


    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )


    print(
        "\nLoading queries..."
    )

    queries=load_queries()

    print(
        f"Query count: {len(queries)}"
    )


    if len(queries)!=120:
        raise RuntimeError(
            "Expected 120 queries"
        )


    print(
        "\nLoading BGE-M3..."
    )


    os.environ[
        "HF_HUB_OFFLINE"
    ]="1"


    model=SentenceTransformer(
        str(MODEL_PATH),
        device="cuda"
    )


    print(
        "Embedding model loaded"
    )


    print(
        "\nConnecting Chroma..."
    )


    client=chromadb.PersistentClient(
        path=str(DB_PATH)
    )


    collection=client.get_collection(
        COLLECTION_NAME
    )


    print(
        "Collection loaded:"
    )

    print(
        COLLECTION_NAME
    )


    recall5=[]
    recall10=[]

    mrr=[]

    predictions=[]


    print(
        "\nRunning retrieval..."
    )


    for index,q in enumerate(
        queries,
        start=1
    ):


        emb=model.encode(
            q["query"],
            normalize_embeddings=True
        )


        result=collection.query(
            query_embeddings=[
                emb.tolist()
            ],
            n_results=TOP_K
        )


        ids=result["ids"][0]


        retrieved=[]


        for rank,cid in enumerate(
            ids,
            start=1
        ):

            retrieved.append(
                {
                    "rank":rank,
                    "chunk_id":cid
                }
            )


        hit5=recall_hit(
            retrieved[:5],
            q["required_any_chunk_ids"]
        )


        hit10=recall_hit(
            retrieved,
            q["required_any_chunk_ids"]
        )


        score_mrr=calculate_mrr(
            retrieved,
            q["required_any_chunk_ids"]
        )


        recall5.append(
            hit5
        )

        recall10.append(
            hit10
        )

        mrr.append(
            score_mrr
        )


        predictions.append(
            {
                "query_id":
                    q["query_id"],

                "query":
                    q["query"],

                "required_any_chunk_ids":
                    q["required_any_chunk_ids"],

                "retrieved":
                    retrieved,

                "hit@5":
                    hit5,

                "hit@10":
                    hit10,

                "mrr":
                    score_mrr
            }
        )


        if index%10==0:

            print(
                f"{index}/120"
            )


    report={

        "phase":
            "Gate B1 Phase4",

        "collection":
            COLLECTION_NAME,

        "model":
            "BAAI/bge-m3",

        "top_k":
            TOP_K,


        "query_count":
            len(queries),


        "recall@5":
            sum(recall5)
            /
            len(recall5),


        "recall@10":
            sum(recall10)
            /
            len(recall10),


        "mrr@10":
            sum(mrr)
            /
            len(mrr),


        "hit_count@5":
            sum(recall5),


        "hit_count@10":
            sum(recall10)

    }


    with open(
        OUTPUT_DIR
        /
        "retrieval_report_v1.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            report,
            f,
            ensure_ascii=False,
            indent=2
        )


    with open(
        OUTPUT_DIR
        /
        "retrieval_predictions_v1.jsonl",
        "w",
        encoding="utf-8"
    ) as f:

        for item in predictions:

            f.write(
                json.dumps(
                    item,
                    ensure_ascii=False
                )
                +
                "\n"
            )


    print("\n")
    print("="*70)
    print("Retrieval Report")
    print("="*70)


    print(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2
        )
    )


    print("\nPASS: Phase4 completed")



if __name__=="__main__":
    main()