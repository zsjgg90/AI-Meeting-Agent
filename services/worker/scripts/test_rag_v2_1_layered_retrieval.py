from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_DIR = PROJECT_ROOT / "data" / "vector_db"

COLLECTION_NAME = "meeting_analyst_rules_v2_1"
EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"

# 所有会议都必须注入的全局证据规则。
GLOBAL_FIXED_IDS = [
    "boundary_rule_012",
]

# 阶段 5.1 分层结构：
# 1 条全局固定规则
# 2 条 POLICY_FIXED 语义召回
# 3 条 RAG_DYNAMIC 语义召回
# 2 条 RAG_SCENARIO 场景召回
EXPECTED_TOTAL = 8
EXPECTED_GLOBAL_FIXED = 1
EXPECTED_POLICY_SELECTED = 2
EXPECTED_DYNAMIC = 3
EXPECTED_SCENARIO = 2

# 86 是正式 v2.1 基线。
# 88 是加入两条 technical_incident 候选规则后的实验状态。
ALLOWED_COLLECTION_COUNTS = {
    86,
    88,
}

EXPECTED_BUCKET_COUNTS = {
    "GLOBAL_FIXED": EXPECTED_GLOBAL_FIXED,
    "POLICY_SELECTED": EXPECTED_POLICY_SELECTED,
    "RAG_DYNAMIC": EXPECTED_DYNAMIC,
    "RAG_SCENARIO": EXPECTED_SCENARIO,
}


@dataclass(frozen=True)
class TestCase:
    name: str
    meeting_type: str
    query: str
    expected_any_ids: tuple[str, ...]


TEST_CASES = [
    TestCase(
        name="需求评审会",
        meeting_type="requirement_review",
        query=(
            "会议提出先取消个性化推荐，但目前只是建议，"
            "没有人明确确认。产品经理要求后端下周补充接口方案。"
        ),
        expected_any_ids=(
            "definition_003",
            "boundary_rule_008",
            "negative_example_002",
            "v4_negative_example_009",
            "positive_example_003",
            "v4_positive_example_001",
        ),
    ),
    TestCase(
        name="项目周会",
        meeting_type="project_weekly",
        query=(
            "本周联调延期，测试资源不足，周五前能否完成还不确定。"
            "关键任务目前没有明确负责人，项目存在延期风险。"
        ),
        expected_any_ids=(
            "boundary_speaker_owner_001",
            "v4_boundary_rule_010",
            "positive_example_015",
            "reasoning_pattern_004",
            "negative_example_010",
            "v4_negative_example_004",
        ),
    ),
    TestCase(
        name="技术故障复盘会",
        meeting_type="technical_incident",
        query=(
            "线上接口大量超时，目前具体根因尚未确认。"
            "会议决定先增加监控，并继续排查缓存策略问题。"
        ),
        expected_any_ids=(
            "technical_incident_boundary_001",
            "technical_incident_boundary_002",
            "v4_positive_example_007",
            "negative_example_007",
        ),
    ),
]


def normalize(value: Any) -> str:
    if value is None:
        return ""

    return " ".join(
        str(value).strip().split()
    )


def embed(
    model: SentenceTransformer,
    text: str,
) -> list[float]:
    return model.encode(
        [text],
        normalize_embeddings=True,
    ).tolist()[0]


def get_global_fixed_rules(
    collection: Any,
) -> list[dict[str, Any]]:
    result = collection.get(
        ids=GLOBAL_FIXED_IDS,
        include=[
            "documents",
            "metadatas",
        ],
    )

    by_id: dict[str, dict[str, Any]] = {}

    for index, chunk_id in enumerate(
        result["ids"]
    ):
        by_id[chunk_id] = {
            "chunk_id": chunk_id,
            "document": result[
                "documents"
            ][index],
            "metadata": result[
                "metadatas"
            ][index],
            "distance": None,
            "retrieval_bucket": (
                "GLOBAL_FIXED"
            ),
        }

    missing_ids = [
        chunk_id
        for chunk_id in GLOBAL_FIXED_IDS
        if chunk_id not in by_id
    ]

    if missing_ids:
        raise RuntimeError(
            "Global fixed rules not found: "
            f"{missing_ids}"
        )

    rows = [
        by_id[chunk_id]
        for chunk_id in GLOBAL_FIXED_IDS
    ]

    for row in rows:
        runtime_layer = normalize(
            row["metadata"].get(
                "runtime_layer"
            )
        )

        if runtime_layer != "POLICY_FIXED":
            raise RuntimeError(
                f"{row['chunk_id']} must use "
                "runtime_layer=POLICY_FIXED, "
                f"actual={runtime_layer}"
            )

    return rows


def build_where_filter(
    runtime_layer: str,
    scenario: str | None,
) -> dict[str, Any]:
    if scenario:
        return {
            "$and": [
                {
                    "runtime_layer":
                    runtime_layer
                },
                {
                    "scenario": scenario
                },
            ]
        }

    return {
        "runtime_layer": runtime_layer
    }


def query_layer(
    collection: Any,
    query_embedding: list[float],
    runtime_layer: str,
    count: int,
    *,
    scenario: str | None = None,
    exclude_ids: set[str] | None = None,
    retrieval_bucket: str | None = None,
) -> list[dict[str, Any]]:
    excluded = exclude_ids or set()

    # 适当多取候选，避免排除固定 ID 后数量不足。
    candidate_count = (
        count
        + len(excluded)
        + 5
    )

    result = collection.query(
        query_embeddings=[
            query_embedding
        ],
        n_results=candidate_count,
        where=build_where_filter(
            runtime_layer,
            scenario,
        ),
        include=[
            "documents",
            "metadatas",
            "distances",
        ],
    )

    ids = result["ids"][0]
    documents = result["documents"][0]
    metadatas = result["metadatas"][0]
    distances = result["distances"][0]

    rows: list[dict[str, Any]] = []

    for index, chunk_id in enumerate(ids):
        if chunk_id in excluded:
            continue

        rows.append(
            {
                "chunk_id": chunk_id,
                "document": documents[index],
                "metadata": metadatas[index],
                "distance": distances[index],
                "retrieval_bucket": (
                    retrieval_bucket
                    or runtime_layer
                ),
            }
        )

        if len(rows) == count:
            break

    if len(rows) != count:
        raise RuntimeError(
            "Insufficient retrieval results: "
            f"runtime_layer={runtime_layer}, "
            f"scenario={scenario}, "
            f"expected={count}, "
            f"actual={len(rows)}"
        )

    return rows


def deduplicate(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen_ids: set[str] = set()
    result: list[dict[str, Any]] = []

    for row in rows:
        chunk_id = row["chunk_id"]

        if chunk_id in seen_ids:
            continue

        seen_ids.add(chunk_id)
        result.append(row)

    return result


def validate_result(
    case: TestCase,
    rows: list[dict[str, Any]],
) -> None:
    if len(rows) != EXPECTED_TOTAL:
        raise AssertionError(
            f"{case.name}: 最终结果应为 "
            f"{EXPECTED_TOTAL} 条，"
            f"实际为 {len(rows)}"
        )

    ids = [
        row["chunk_id"]
        for row in rows
    ]

    if len(ids) != len(set(ids)):
        raise AssertionError(
            f"{case.name}: 出现重复 chunk_id"
        )

    bucket_counts = {
        bucket: 0
        for bucket in (
            EXPECTED_BUCKET_COUNTS
        )
    }

    for row in rows:
        bucket = normalize(
            row.get(
                "retrieval_bucket"
            )
        )

        if bucket not in bucket_counts:
            raise AssertionError(
                f"{case.name}: 未知召回分组 "
                f"{bucket}"
            )

        bucket_counts[bucket] += 1

    if (
        bucket_counts
        != EXPECTED_BUCKET_COUNTS
    ):
        raise AssertionError(
            f"{case.name}: 分层数量错误，"
            f"expected="
            f"{EXPECTED_BUCKET_COUNTS}, "
            f"actual={bucket_counts}"
        )

    global_rows = [
        row
        for row in rows
        if row.get(
            "retrieval_bucket"
        ) == "GLOBAL_FIXED"
    ]

    global_ids = {
        row["chunk_id"]
        for row in global_rows
    }

    if global_ids != set(
        GLOBAL_FIXED_IDS
    ):
        raise AssertionError(
            f"{case.name}: 全局固定规则错误，"
            f"expected={GLOBAL_FIXED_IDS}, "
            f"actual={sorted(global_ids)}"
        )

    policy_rows = [
        row
        for row in rows
        if row.get(
            "retrieval_bucket"
        ) == "POLICY_SELECTED"
    ]

    for row in policy_rows:
        runtime_layer = normalize(
            row["metadata"].get(
                "runtime_layer"
            )
        )

        if runtime_layer != "POLICY_FIXED":
            raise AssertionError(
                f"{case.name}: POLICY_SELECTED "
                "来源层错误，"
                f"{row['chunk_id']}="
                f"{runtime_layer}"
            )

        if (
            row["chunk_id"]
            in GLOBAL_FIXED_IDS
        ):
            raise AssertionError(
                f"{case.name}: 全局固定规则被"
                "重复语义召回，"
                f"chunk_id={row['chunk_id']}"
            )

    dynamic_rows = [
        row
        for row in rows
        if row.get(
            "retrieval_bucket"
        ) == "RAG_DYNAMIC"
    ]

    for row in dynamic_rows:
        runtime_layer = normalize(
            row["metadata"].get(
                "runtime_layer"
            )
        )

        if runtime_layer != "RAG_DYNAMIC":
            raise AssertionError(
                f"{case.name}: 动态规则层错误，"
                f"{row['chunk_id']}="
                f"{runtime_layer}"
            )

    scenario_rows = [
        row
        for row in rows
        if row.get(
            "retrieval_bucket"
        ) == "RAG_SCENARIO"
    ]

    for row in scenario_rows:
        runtime_layer = normalize(
            row["metadata"].get(
                "runtime_layer"
            )
        )

        actual_scenario = normalize(
            row["metadata"].get(
                "scenario"
            )
        )

        if runtime_layer != "RAG_SCENARIO":
            raise AssertionError(
                f"{case.name}: 场景规则层错误，"
                f"{row['chunk_id']}="
                f"{runtime_layer}"
            )

        if (
            actual_scenario
            != case.meeting_type
        ):
            raise AssertionError(
                f"{case.name}: 场景规则不匹配，"
                f"{row['chunk_id']}="
                f"{actual_scenario}"
            )

    if not set(ids).intersection(
        case.expected_any_ids
    ):
        raise AssertionError(
            f"{case.name}: 未命中预期关键规则，"
            f"actual_ids={ids}"
        )


def print_result(
    case: TestCase,
    rows: list[dict[str, Any]],
) -> None:
    print()
    print("=" * 120)
    print(
        f"{case.name} | "
        f"meeting_type="
        f"{case.meeting_type}"
    )
    print("=" * 120)
    print("Query:", case.query)
    print()

    for index, row in enumerate(
        rows,
        start=1,
    ):
        metadata = row["metadata"]
        distance = row["distance"]

        distance_text = (
            "fixed"
            if distance is None
            else f"{distance:.4f}"
        )

        print(
            f"{index:>2}. "
            f"{row['chunk_id']:<34} "
            f"bucket="
            f"{row.get('retrieval_bucket', ''):<16} "
            f"layer="
            f"{metadata.get('runtime_layer', ''):<14} "
            f"scenario="
            f"{metadata.get('scenario', ''):<26} "
            f"dimension="
            f"{metadata.get('dimension', ''):<22} "
            f"type="
            f"{metadata.get('knowledge_type', ''):<20} "
            f"distance={distance_text}"
        )


def main() -> int:
    print("Project root:", PROJECT_ROOT)
    print("Vector DB:", DB_DIR)
    print("Collection:", COLLECTION_NAME)
    print(
        "Embedding model:",
        EMBEDDING_MODEL,
    )

    model = SentenceTransformer(
        EMBEDDING_MODEL
    )

    client = chromadb.PersistentClient(
        path=str(DB_DIR)
    )

    collection = client.get_collection(
        COLLECTION_NAME
    )

    collection_count = collection.count()

    print(
        "Collection count:",
        collection_count,
    )

    if (
        collection_count
        not in ALLOWED_COLLECTION_COUNTS
    ):
        raise RuntimeError(
            "v2.1 experiment collection count "
            "must be one of "
            f"{sorted(ALLOWED_COLLECTION_COUNTS)}, "
            f"actual={collection_count}"
        )

    global_fixed_rows = (
        get_global_fixed_rules(
            collection
        )
    )

    global_fixed_ids = {
        row["chunk_id"]
        for row in global_fixed_rows
    }

    all_result_ids: list[
        tuple[str, ...]
    ] = []

    policy_signatures: list[
        tuple[str, ...]
    ] = []

    dynamic_scenario_signatures: list[
        tuple[str, ...]
    ] = []

    for case in TEST_CASES:
        query_embedding = embed(
            model,
            case.query,
        )

        policy_selected_rows = (
            query_layer(
                collection=collection,
                query_embedding=(
                    query_embedding
                ),
                runtime_layer=(
                    "POLICY_FIXED"
                ),
                count=(
                    EXPECTED_POLICY_SELECTED
                ),
                exclude_ids=(
                    global_fixed_ids
                ),
                retrieval_bucket=(
                    "POLICY_SELECTED"
                ),
            )
        )

        dynamic_rows = query_layer(
            collection=collection,
            query_embedding=(
                query_embedding
            ),
            runtime_layer=(
                "RAG_DYNAMIC"
            ),
            count=EXPECTED_DYNAMIC,
            retrieval_bucket=(
                "RAG_DYNAMIC"
            ),
        )

        scenario_rows = query_layer(
            collection=collection,
            query_embedding=(
                query_embedding
            ),
            runtime_layer=(
                "RAG_SCENARIO"
            ),
            scenario=case.meeting_type,
            count=EXPECTED_SCENARIO,
            retrieval_bucket=(
                "RAG_SCENARIO"
            ),
        )

        final_rows = deduplicate(
            global_fixed_rows
            + policy_selected_rows
            + dynamic_rows
            + scenario_rows
        )

        validate_result(
            case,
            final_rows,
        )

        print_result(
            case,
            final_rows,
        )

        result_ids = tuple(
            row["chunk_id"]
            for row in final_rows
        )

        all_result_ids.append(
            result_ids
        )

        policy_signatures.append(
            tuple(
                row["chunk_id"]
                for row in (
                    policy_selected_rows
                )
            )
        )

        dynamic_scenario_signatures.append(
            tuple(
                row["chunk_id"]
                for row in (
                    dynamic_rows
                    + scenario_rows
                )
            )
        )

    if (
        len(set(all_result_ids))
        != len(TEST_CASES)
    ):
        raise AssertionError(
            "三类会议的最终 Top-8 "
            "存在完全相同结果"
        )

    if (
        len(
            set(
                dynamic_scenario_signatures
            )
        )
        != len(TEST_CASES)
    ):
        raise AssertionError(
            "三类会议的动态+场景召回结果"
            "不具备差异性"
        )

    unique_policy_signatures = len(
        set(policy_signatures)
    )

    print()
    print("=" * 120)
    print(
        "Layered retrieval 5.1 "
        "validation passed"
    )
    print("=" * 120)
    print("Cases:", len(TEST_CASES))
    print(
        "Per case:",
        f"{EXPECTED_GLOBAL_FIXED} "
        "global fixed + "
        f"{EXPECTED_POLICY_SELECTED} "
        "policy selected + "
        f"{EXPECTED_DYNAMIC} dynamic + "
        f"{EXPECTED_SCENARIO} scenario = "
        f"{EXPECTED_TOTAL}",
    )
    print(
        "No duplicate IDs: passed"
    )
    print(
        "Scenario filters: passed"
    )
    print(
        "Retrieval differentiation: "
        "passed"
    )
    print(
        "Unique policy signatures:",
        unique_policy_signatures,
        "/",
        len(TEST_CASES),
    )

    if unique_policy_signatures == 1:
        print(
            "Warning: POLICY_SELECTED "
            "results are identical for all cases."
        )
    else:
        print(
            "Policy semantic selection: "
            "differentiated"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())