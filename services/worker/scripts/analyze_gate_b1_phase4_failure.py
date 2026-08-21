import json
from pathlib import Path


pred = Path(
"data/rag/gate_b_v3_3/phase4/retrieval_predictions_v1.jsonl"
)


output = Path(
"data/rag/gate_b_v3_3/phase4/failure_analysis.json"
)


failures=[]


with open(pred,encoding="utf-8") as f:

    for line in f:

        item=json.loads(line)

        if not item["hit@10"]:

            failures.append(
                {
                    "query_id":
                        item["query_id"],

                    "query":
                        item["query"],

                    "required":
                        item["required_any_chunk_ids"],

                    "retrieved":
                        [
                            x["chunk_id"]
                            for x in item["retrieved"]
                        ]
                }
            )


with open(
    output,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        failures,
        f,
        ensure_ascii=False,
        indent=2
    )


print(
    "failed:",
    len(failures)
)

print(
    "output:",
    output
)