from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.agent_tools import (
    AgentTool,
    AnalyzeMeetingTool,
    GetMeetingContextTool,
    GetOpenActionItemsTool,
    SearchMeetingHistoryTool,
    SearchProjectKnowledgeTool,
    ValidateMeetingAnalysisTool,
)
from app.agent_tools.base import ToolPolicy


class ToolRegistryError(Exception):
    """Base error for Agent Tool Registry failures."""


class UnknownToolError(ToolRegistryError, KeyError):
    """Raised when a requested tool is not registered."""


class ToolRegistryPolicyError(ToolRegistryError, ValueError):
    """Raised when a registered tool violates runtime policy boundaries."""


class ToolRegistry:
    def __init__(self, tools: tuple[AgentTool, ...] | None = None) -> None:
        self._tools: dict[str, AgentTool] = {}
        for tool in tools or ():
            self.register(tool)

    def register(self, tool: AgentTool) -> None:
        self._validate_tool(tool)
        if tool.name in self._tools:
            raise ToolRegistryError(f"Duplicate Agent tool registration: {tool.name}")
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> AgentTool:
        if name not in self._tools:
            raise UnknownToolError(f"Unknown Agent tool: {name}")
        return self._tools[name]

    def list_tools(self) -> tuple[AgentTool, ...]:
        return tuple(self._tools.values())

    def list_tool_names(self) -> tuple[str, ...]:
        return tuple(self._tools.keys())

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def _validate_tool(self, tool: AgentTool) -> None:
        if not isinstance(tool.name, str) or not tool.name.strip():
            raise ToolRegistryPolicyError("Agent tool name must be a non-empty string.")
        if not isinstance(tool.policy, ToolPolicy):
            raise ToolRegistryPolicyError(f"Agent tool {tool.name} has an invalid ToolPolicy.")
        if tool.policy.has_side_effects:
            raise ToolRegistryPolicyError(f"Agent tool {tool.name} declares side effects.")
        if tool.policy.requires_confirmation:
            raise ToolRegistryPolicyError(f"Agent tool {tool.name} requires confirmation and is not allowed in Phase 4A.")


def create_default_tool_registry(
    *,
    db_provider: Callable[[], Any],
    retriever_factory: Callable[[], Any] | None = None,
    analysis_service_factory: Callable[[], Any] | None = None,
    validator: Callable[[dict[str, Any], str], tuple[dict[str, Any], list[dict[str, Any]]]] | None = None,
) -> ToolRegistry:
    return ToolRegistry(
        (
            GetMeetingContextTool(db_provider=db_provider),
            SearchMeetingHistoryTool(db_provider=db_provider),
            SearchProjectKnowledgeTool(retriever_factory=retriever_factory),
            GetOpenActionItemsTool(db_provider=db_provider),
            AnalyzeMeetingTool(service_factory=analysis_service_factory),
            ValidateMeetingAnalysisTool(validator=validator),
        )
    )


__all__ = [
    "ToolRegistry",
    "ToolRegistryError",
    "ToolRegistryPolicyError",
    "UnknownToolError",
    "create_default_tool_registry",
]
