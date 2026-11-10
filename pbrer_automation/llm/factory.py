"""
Selects which ToolCallingProvider every agent actually gets, based on
`settings.llm.provider`. Previously nothing read that setting -- each
agent's `provider_factory` constructor arg defaulted to None and the
pipeline never passed one, so `PBRER_LLM_PROVIDER=bedrock` had no effect.
"""
from __future__ import annotations

from typing import Any, Callable

from config.settings import settings
from llm.local_provider import LocalDeterministicProvider
from llm.provider import AgentStep, ToolSpec


def build_provider_factory() -> Callable[[Callable[[list[dict[str, Any]], list[ToolSpec]], AgentStep]], Any]:
    """Returns provider_factory(policy) -> ToolCallingProvider. The signature
    stays uniform across providers even though BedrockProvider ignores
    `policy` entirely -- a real model decides instead of a rule-based
    Python policy function."""
    if settings.llm.provider == "bedrock":
        from llm.bedrock_provider import BedrockProvider

        def factory(policy):  # noqa: ARG001 -- unused, see docstring
            return BedrockProvider()

        return factory

    def factory(policy):
        return LocalDeterministicProvider(policy)

    return factory
