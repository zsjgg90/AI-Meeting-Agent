from pydantic import BaseModel
from typing import List


class SemanticContext(BaseModel):

    event_type: str

    decision_commitment: str

    action_commitment: str

    decision_status: str

    action_status: str

    risk_status: str

    allowed_dimensions: List[str]

    confidence: float



class BoundaryResult(BaseModel):

    can_be_decision: bool

    can_be_action: bool

    can_be_risk: bool

    boundary_type: str

    reason: str

    confidence: float

class RulePlan(BaseModel):
    """
    Rule Plan（规则规划结果）

    输出给 RAG Retrieval（检索增强生成检索）
    """

    query_intent: str

    rule_domains: List[str]

    dimension: str

    retrieval_keywords: List[str]

    confidence: float