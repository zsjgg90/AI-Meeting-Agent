import json
from pathlib import Path
from datetime import datetime


ROOT = Path(__file__).resolve().parents[3]


INPUT_FILE = (
    ROOT
    / "data"
    / "rag"
    / "gate_b_v3_4"
    / "baseline_v3_3_backup.jsonl"
)


OUTPUT_FILE = (
    ROOT
    / "data"
    / "rag"
    / "gate_b_v3_4"
    / "meeting_analyst_rag_v3_4_0_candidate.jsonl"
)


def detect_dimension(item):

    text = (
        item.get("title", "")
        + " "
        + item.get("content", "")
    ).lower()


    if any(
        k in text
        for k in [
            "decision",
            "决定",
            "确认",
            "采用",
            "拍板"
        ]
    ):
        return "decision"


    if any(
        k in text
        for k in [
            "action",
            "任务",
            "负责人",
            "完成"
        ]
    ):
        return "action"


    if any(
        k in text
        for k in [
            "risk",
            "风险",
            "压力"
        ]
    ):
        return "risk"


    if any(
        k in text
        for k in [
            "source",
            "evidence",
            "证据"
        ]
    ):
        return "evidence"


    return "general"



def build_rule_pack(item, index):

    dimension = detect_dimension(item)


    title = item.get(
        "title",
        item.get(
            "content",
            ""
        )[:50]
    )


    content = item.get(
        "content",
        ""
    )


    return {

        "chunk_id":
            f"v34_rule_pack_{index:04d}",


        "schema_version":
            "rag-rule-pack-v3_4",


        "chunk_type":
            "rule_pack",


        "dimension":
            dimension,


        "title":
            title,


        "definition":
            content,


        "decision_rule":
            "",


        "positive_examples":
            [],


        "negative_examples":
            [],


        "keywords":
            [],


        "source_chunk_id":
            item.get(
                "chunk_id",
                ""
            ),


        "created_at":
            datetime.utcnow().isoformat()

    }



def main():

    print("="*70)
    print("Gate B1 Phase4.2 Rule Pack Builder")
    print("="*70)


    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            INPUT_FILE
        )


    rows=[]


    with INPUT_FILE.open(
        "r",
        encoding="utf-8"
    ) as f:

        for line in f:

            if line.strip():

                rows.append(
                    json.loads(line)
                )


    print(
        "Input chunks:",
        len(rows)
    )


    output=[]


    for idx,item in enumerate(rows,1):

        output.append(
            build_rule_pack(
                item,
                idx
            )
        )


    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8"
    ) as f:

        for item in output:

            f.write(
                json.dumps(
                    item,
                    ensure_ascii=False
                )
                + "\n"
            )


    print(
        "Output chunks:",
        len(output)
    )


    print(
        "Output:",
        OUTPUT_FILE
    )


    print(
        "STATUS: PASS"
    )



if __name__ == "__main__":
    main()