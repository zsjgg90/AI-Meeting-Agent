from app.semantic_intelligence.dimension_mapper import (
    map_dimension
)



cases=[

"key_conclusions",

"action_items",

"risks_and_focus",

"meeting_summary"

]



for item in cases:

    print(
        item,
        "=>",
        map_dimension(item)
    )