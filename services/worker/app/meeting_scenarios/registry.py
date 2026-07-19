from __future__ import annotations

from app.agent_contract import MeetingType
from app.meeting_scenarios.base import MeetingScenarioPolicy
from app.meeting_scenarios.cross_department import POLICY as CROSS_DEPARTMENT_POLICY
from app.meeting_scenarios.customer_requirement import POLICY as CUSTOMER_REQUIREMENT_POLICY
from app.meeting_scenarios.management_decision import POLICY as MANAGEMENT_DECISION_POLICY
from app.meeting_scenarios.project_retrospective import POLICY as PROJECT_RETROSPECTIVE_POLICY
from app.meeting_scenarios.project_weekly import POLICY as PROJECT_WEEKLY_POLICY
from app.meeting_scenarios.requirement_review import POLICY as REQUIREMENT_REVIEW_POLICY
from app.meeting_scenarios.technical_review import POLICY as TECHNICAL_REVIEW_POLICY
from app.meeting_scenarios.unknown import POLICY as UNKNOWN_POLICY
from app.meeting_scenarios.version_planning import POLICY as VERSION_PLANNING_POLICY


class MeetingScenarioRegistry:
    def __init__(self, policies: tuple[MeetingScenarioPolicy, ...]) -> None:
        self._policies: dict[MeetingType, MeetingScenarioPolicy] = {}
        for policy in policies:
            self.register(policy)

    def register(self, policy: MeetingScenarioPolicy) -> None:
        if policy.meeting_type in self._policies:
            raise ValueError(f"Duplicate meeting scenario policy: {policy.meeting_type}")
        self._policies[policy.meeting_type] = policy

    def get_policy(self, meeting_type: MeetingType) -> MeetingScenarioPolicy:
        if meeting_type not in self._policies:
            raise KeyError(f"Unknown meeting scenario policy: {meeting_type}")
        return self._policies[meeting_type]

    def list_policies(self) -> tuple[MeetingScenarioPolicy, ...]:
        return tuple(self._policies.values())

    def has_policy(self, meeting_type: MeetingType) -> bool:
        return meeting_type in self._policies


DEFAULT_POLICIES: tuple[MeetingScenarioPolicy, ...] = (
    REQUIREMENT_REVIEW_POLICY,
    PROJECT_WEEKLY_POLICY,
    TECHNICAL_REVIEW_POLICY,
    VERSION_PLANNING_POLICY,
    CROSS_DEPARTMENT_POLICY,
    PROJECT_RETROSPECTIVE_POLICY,
    MANAGEMENT_DECISION_POLICY,
    CUSTOMER_REQUIREMENT_POLICY,
    UNKNOWN_POLICY,
)

_DEFAULT_REGISTRY = MeetingScenarioRegistry(DEFAULT_POLICIES)


def get_policy(meeting_type: MeetingType) -> MeetingScenarioPolicy:
    return _DEFAULT_REGISTRY.get_policy(meeting_type)


def list_policies() -> tuple[MeetingScenarioPolicy, ...]:
    return _DEFAULT_REGISTRY.list_policies()


def has_policy(meeting_type: MeetingType) -> bool:
    return _DEFAULT_REGISTRY.has_policy(meeting_type)


__all__ = [
    "DEFAULT_POLICIES",
    "MeetingScenarioRegistry",
    "get_policy",
    "list_policies",
    "has_policy",
]
