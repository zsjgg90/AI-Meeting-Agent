import json
from pathlib import Path
from datetime import datetime, timezone


INPUT = Path(
    "data/rag/gate_b_v3_4/meeting_analyst_rag_v3_4_0_candidate.jsonl"
)

OUTPUT = Path(
    "data/rag/gate_b_v3_4/meeting_analyst_rag_v3_4_1_enriched.jsonl"
)


# 手工规则增强模板
ENRICH_RULES = {

    "decision": {
        "decision_rule": [
            "只有明确确认、采用、批准、执行才属于decision",
            "proposal不能自动升级为decision",
            "讨论方向不能生成最终结论"
        ],
        "positive_examples":[
            "确认采用这个方案",
            "决定下周上线",
            "大家同意按照方案A执行"
        ],
        "negative_examples":[
            "可以考虑",
            "是不是可以",
            "后面研究一下"
        ],
        "keywords":[
            "确认",
            "决定",
            "同意",
            "采用",
            "批准"
        ]
    },


    "action_item":{
        "decision_rule":[
            "必须存在负责人或明确执行动作",
            "提醒关注不等于待办"
        ],
        "positive_examples":[
            "张三负责完成测试",
            "李四今天提交报告"
        ],
        "negative_examples":[
            "关注一下",
            "后续看看",
            "有时间处理"
        ],
        "keywords":[
            "负责",
            "安排",
            "完成",
            "提交"
        ]
    },


    "risk":{
        "decision_rule":[
            "风险必须包含潜在影响或不确定性",
            "已经发生的问题不直接归类风险"
        ],
        "positive_examples":[
            "用户增长后可能导致服务器压力",
            "长文本可能影响性能"
        ],
        "negative_examples":[
            "已经出现加载慢",
            "当前测试失败"
        ],
        "keywords":[
            "可能",
            "风险",
            "影响",
            "压力"
        ]
    }

}



def main():

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    count = 0


    with INPUT.open(
        "r",
        encoding="utf-8"
    ) as fin, OUTPUT.open(
        "w",
        encoding="utf-8"
    ) as fout:


        for line in fin:

            item=json.loads(line)


            dimension=item.get(
                "dimension"
            )


            enrich=ENRICH_RULES.get(
                dimension
            )


            if enrich:

                item.update(enrich)


            else:

                item.setdefault(
                    "decision_rule",
                    []
                )

                item.setdefault(
                    "positive_examples",
                    []
                )

                item.setdefault(
                    "negative_examples",
                    []
                )

                item.setdefault(
                    "keywords",
                    []
                )


            item["updated_at"]=datetime.now(
                timezone.utc
            ).isoformat()


            fout.write(
                json.dumps(
                    item,
                    ensure_ascii=False
                )
                + "\n"
            )

            count+=1


    print("="*70)
    print("Gate B1 Phase4.3 Rule Enrichment")
    print("="*70)
    print("Input :", INPUT)
    print("Output:", OUTPUT)
    print("Chunks:", count)
    print("STATUS: PASS")



if __name__=="__main__":
    main()