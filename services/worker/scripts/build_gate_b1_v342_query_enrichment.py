import json
from pathlib import Path
from datetime import datetime, timezone


INPUT = Path(
    r"D:\codex_work\会议声纹识别\data\rag\gate_b_v3_4_2\meeting_analyst_rag_v3_4_2_candidate.jsonl"
)


OUTPUT = Path(
    r"D:\codex_work\会议声纹识别\data\rag\gate_b_v3_4_2\meeting_analyst_rag_v3_4_2_enriched.jsonl"
)



QUERY_PATTERNS = {


"decision":[

"是不是可以考虑",

"这个方案是否可行",

"大家觉得怎么样",

"要不要做",

"先研究一下",

"后面再决定",

"可以先看看"

],


"action":[

"后面跟一下",

"关注一下",

"有时间处理",

"安排一下",

"谁负责",

"后续推进"

],


"risk":[

"可能会导致",

"以后可能",

"如果用户增长",

"存在风险",

"压力比较大"

],


"unresolved_issue":[

"目前还有问题",

"还没有解决",

"需要确认",

"还没定",

"不知道怎么处理"

]

}



def main():


    count=0


    with open(
        INPUT,
        "r",
        encoding="utf-8"
    ) as f, open(
        OUTPUT,
        "w",
        encoding="utf-8"
    ) as out:


        for line in f:


            row=json.loads(line)


            dimension=row.get(
                "dimension",
                ""
            )


            patterns=[]


            for key,value in QUERY_PATTERNS.items():


                if key in dimension:

                    patterns.extend(value)



            row["query_patterns"]=patterns


            row["schema_version"]="rag-rule-pack-v3_4_2"



            out.write(

                json.dumps(
                    row,
                    ensure_ascii=False
                )
                +
                "\n"

            )


            count+=1



    print(
        "Output:",
        OUTPUT
    )


    print(
        "Chunks:",
        count
    )



if __name__=="__main__":

    main()