"""
Tool-calling provider abstraction.

Every "understanding" agent (Excel, Document) runs the SAME loop shape,
regardless of which provider executes it:

    1. agent gives the provider: a system prompt (its role/objective),
       the running conversation/observation history, and the list of
       predefined tools it's allowed to use.
    2. provider.decide(...) returns ONE AgentStep: either "call this tool
       with these arguments" or "I'm done, here is my final structured
       output".
    3. if it's a tool call, the agent's own code (never the provider)
       executes the actual predefined Python tool and appends the result
       to history.
    4. repeat until final, or max_iterations is hit.

Two providers implement this interface:
  - BedrockProvider: real LLM tool-calling via AWS Bedrock Converse API.
  - LocalDeterministicProvider: a transparent, clearly-labeled fallback
    that runs the identical loop using a rule-based policy function
    supplied by the agent (not a generic "fake LLM"), so the architecture
    is exercised end-to-end even when Bedrock access is unavailable.

No tool is ever invented by a provider: tools are predefined, typed
Python callables (ToolSpec.fn) and the provider only ever selects AMONG
them by name -- it cannot execute arbitrary code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Protocol


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters_schema: dict[str, Any]  # JSON schema for the tool's arguments
    fn: Callable[..., Any]
    library: str = ""  # e.g. "openpyxl", "pandas" -- shown in traceability UI


@dataclass
class AgentStep:
    type: Literal["call_tool", "final"]
    tool_name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    final_output: dict[str, Any] | None = None
    # Set by BedrockProvider from the real Converse API toolUse block it
    # generated this step from (None for LocalDeterministicProvider steps,
    # which never flow through Converse). Threading this through lets the
    # NEXT turn be rebuilt as a real toolUse/toolResult pair instead of
    # flattened text -- see llm.bedrock_provider._to_converse_messages.
    tool_use_id: str | None = None


class ToolCallingProvider(Protocol):
    mode: str  # "bedrock" | "local_deterministic"

    def decide(
        self,
        system_prompt: str,
        conversation: list[dict[str, Any]],
        tools: list[ToolSpec],
    ) -> AgentStep:
        ...
