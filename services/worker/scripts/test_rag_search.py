from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer


SCRIPT_FILE = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_FILE.parents[3]

DB_DIR = PROJECT_ROOT / "data" / "vector_db"

COLLECTION_NAME = "meeting_analyst_rules"
EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"


def search(query: str, top_k: int = 5):
    model = SentenceTransformer(EMBEDDING_MODEL)

    client = chromadb.PersistentClient(path=str(DB_DIR))
    collection = client.get_collection(name=COLLECTION_NAME)

    query_embedding = model.encode(
        [query],
        normalize_embeddings=True
    ).tolist()[0]

    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )

    rows = []

    for i in range(len(result["ids"][0])):
        meta = result["metadatas"][0][i]
        distance = result["distances"][0][i]

        rows.append({
            "rank": i + 1,
            "chunk_id": result["ids"][0][i],
            "title": meta.get("title", ""),
            "section": meta.get("section", ""),
            "knowledge_type": meta.get("knowledge_type", ""),
            "distance": round(distance, 4),
        })

    return rows


if __name__ == "__main__":
    queries = [
        "待办和遗留问题怎么区分",
        "已经存在的问题和未来风险怎么区分",
        "建议是否属于核心结论",
        "没有负责人和截止时间的任务怎么分类",
        "批量下载没有限流有什么风险",
    ]

    print("DB_DIR:", DB_DIR)

    for query in queries:
        print("\n" + "=" * 80)
        print("QUERY:", query)
        print("=" * 80)

        results = search(query, top_k=5)

        for item in results:
            print(
                f"{item['rank']}. {item['title']} | "
                f"{item['section']} | "
                f"{item['knowledge_type']} | "
                f"distance={item['distance']}"
            )