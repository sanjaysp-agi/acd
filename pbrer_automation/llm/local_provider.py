"""
LocalDeterministicProvider: the honest, clearly-labeled fallback used
whenever Bedrock access is unavailable or disabled.

This is NOT a fake/simulated LLM. It runs the exact same decide() contract
as BedrockProvider, but the "which tool next, given what we've observed so
far" decision is made by a rule-based policy function the calling agent
supplies -- because without a real model there is no generic way to reason
over arbitrary tool descriptions in natural language. Every agent that
wants to run in local mode must provide its own `policy(conversation,
tools) -> AgentStep`, which is allowed to branch on actual prior tool
results (this tenant's workbook turned out to have 3 sheets, so inspect
all 3; a column mapping came back needs_review, so flag it) -- i.e. real
conditional behaviour, just expressed in Python instead of free-text model
reasoning.
"""
from __future__ import annotations

from typing import Any, Callable

from llm.provider import AgentStep, ToolSpec


class LocalDeterministicProvider:
    mode = "local_deterministic"

    def __init__(self, policy: Callable[[list[dict[str, Any]], list[ToolSpec]], AgentStep]):
        self._policy = policy

    def decide(
        self,
        system_prompt: str,
        conversation: list[dict[str, Any]],
        tools: list[ToolSpec],
    ) -> AgentStep:
        return self._policy(conversation, tools)
