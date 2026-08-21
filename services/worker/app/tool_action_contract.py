from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.action_proposal_engine import ActionCandidate


ExecutionMode = Literal["disabled"]


class ToolActionContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    required_permissions: list[str] = Field(default_factory=list)
    confirmation_required: bool
    execution_mode: ExecutionMode = "disabled"
    blocked_reason: list[str] = Field(default_factory=list)


class ToolActionContractBuilder:
    _TOOL_BY_ACTION = {
        "create_task": "task.create",
        "update_task": "task.update",
        "notify_owner": "notify.owner",
        "search_information": "knowledge.search",
    }
    _PERMISSIONS_BY_TOOL = {
        "task.create": ["task:create", "audit:write"],
        "task.update": ["task:update", "audit:write"],
        "notify.owner": ["notification:prepare", "notification:send", "audit:write"],
        "knowledge.search": ["knowledge:search", "audit:write"],
    }

    def build(self, candidates: list[ActionCandidate]) -> list[ToolActionContract]:
        return [self._contract_for(candidate) for candidate in candidates]

    def _contract_for(self, candidate: ActionCandidate) -> ToolActionContract:
        tool_id = self._TOOL_BY_ACTION.get(candidate.action_type)
        blocked_reason = [
            "stage8_5_4_shadow_only",
            "execution_not_attempted",
            "no_execution_adapter",
            "writes_disabled",
        ]
        if tool_id is None:
            tool_id = f"unsupported.{candidate.action_type}"
            blocked_reason.append("tool_not_whitelisted")

        required_permissions = self._required_permissions(tool_id, candidate)
        blocked_reason.extend(candidate.permission_state.blocked_reasons)
        if candidate.requires_confirmation:
            blocked_reason.append("human_confirmation_required")
        if not required_permissions:
            blocked_reason.append("required_permissions_missing")

        return ToolActionContract(
            tool_id=tool_id,
            action_id=candidate.action_id,
            required_permissions=required_permissions,
            confirmation_required=candidate.requires_confirmation,
            execution_mode="disabled",
            blocked_reason=self._unique(blocked_reason),
        )

    def _required_permissions(self, tool_id: str, candidate: ActionCandidate) -> list[str]:
        permissions = list(self._PERMISSIONS_BY_TOOL.get(tool_id) or candidate.permission_state.required_permissions)
        if tool_id.startswith("unsupported."):
            return permissions
        if "audit:write" not in permissions:
            permissions.append("audit:write")
        return self._unique(permissions)

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result


def action_shadow_audit_payload(
    *,
    meeting_id: str,
    candidates: list[ActionCandidate],
    contracts: list[ToolActionContract],
) -> dict[str, object]:
    blocked_reasons = ToolActionContractBuilder._unique(
        [reason for contract in contracts for reason in contract.blocked_reason]
    )
    return {
        "meeting_id": meeting_id,
        "candidate_count": len(candidates),
        "contract_count": len(contracts),
        "execution_attempted": False,
        "blocked_reason": blocked_reasons,
        "writes_performed": False,
    }


__all__ = [
    "ToolActionContract",
    "ToolActionContractBuilder",
    "action_shadow_audit_payload",
]
