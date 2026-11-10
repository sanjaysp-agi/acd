"""
Generic tool-calling agent runner shared by every "understanding" agent.

The loop is provider-agnostic: it does not know or care whether
`provider.decide(...)` is backed by a live Bedrock model or a local
deterministic policy. It only knows how to:
  1. ask the provider for the next step given the conversation so far,
  2. if it's a tool call, execute the named tool (and ONLY a tool present
     in `tools` -- never arbitrary code) and record the call,
  3. append a structured tool-result turn to the conversation,
  4. stop at `final` or at `max_iterations`.

This is also where every ToolCallRecord gets written to the observability
trace store, so the frontend's Agent Execution & Traceability page is
reading real invocations, never fabricated ones.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, UTC
from typing import Any, Callable

from llm.provider import AgentStep, ToolCallingProvider, ToolSpec
from models.schemas import AgentRunResult, AgentWarning, ToolCallRecord


class ToolExecutionError(RuntimeError):
    pass


class ToolCallingAgent:
    agent_name = "base_agent"

    def __init__(self, provider: ToolCallingProvider, tools: list[ToolSpec], max_iterations: int = 10,
                 trace_sink: Callable[[dict[str, Any]], None] | None = None):
        self.provider = provider
        self.tools = {t.name: t for t in tools}
        self.max_iterations = max_iterations
        self.trace_sink = trace_sink or (lambda event: None)

    def _emit(self, run_id: str, event_type: str, **kwargs) -> None:
        self.trace_sink(
            {
                "run_id": run_id,
                "timestamp": datetime.now(UTC),
                "agent_name": self.agent_name,
                "event_type": event_type,
                **kwargs,
            }
        )

    @staticmethod
    def _redact(arguments: dict[str, Any]) -> dict[str, Any]:
        """Redact anything that looks like a raw file path's parent dirs or
        patient-level content; keep file NAMES and structural arguments
        (row numbers, sheet names) visible, since those are what the
        traceability UI needs to show."""
        redacted = {}
        for k, v in arguments.items():
            if isinstance(v, str) and ("\\" in v or "/" in v):
                redacted[k] = v.split("\\")[-1].split("/")[-1]
            else:
                redacted[k] = v
        return redacted

    def run(self, run_id: str, system_prompt: str, initial_task: str) -> AgentRunResult:
        result = AgentRunResult(
            agent_name=self.agent_name,
            run_id=run_id,
            status="running",
            started_at=datetime.now(UTC),
            input_summary=initial_task,
            mode=self.provider.mode,
        )
        self._emit(run_id, "agent_started", message=initial_task, status="info")

        conversation: list[dict[str, Any]] = [{"role": "user", "content": initial_task}]

        for iteration in range(self.max_iterations):
            step = self.provider.decide(system_prompt, conversation, list(self.tools.values()))

            if step.type == "final":
                result.status = "completed"
                result.completed_at = datetime.now(UTC)
                result.output = step.final_output or {}
                self._emit(run_id, "agent_completed", status="success",
                           structured_output=result.output)
                return result

            tool = self.tools.get(step.tool_name)
            if tool is None:
                warning = AgentWarning(
                    code="unknown_tool_requested",
                    message=f"Provider requested unknown tool '{step.tool_name}'; ignoring.",
                    severity="warning",
                )
                result.warnings.append(warning)
                self._emit(run_id, "warning", message=warning.message, status="warning")
                # Shaped like a real tool-result turn (same tool_use_id the
                # model's own toolUse block carried) so Converse-native
                # providers can reply with a matching toolResult instead of
                # leaving a dangling toolUse with no response.
                conversation.append({
                    "role": "user",
                    "content": f"[invalid tool request: {step.tool_name}]",
                    "tool_use_id": step.tool_use_id,
                    "tool_name": step.tool_name,
                    "error": f"Unknown tool '{step.tool_name}'",
                })
                continue

            started = time.monotonic()
            try:
                tool_result = tool.fn(**step.arguments)
                error = None
            except Exception as exc:  # noqa: BLE001 -- captured into trace, never silently swallowed
                tool_result = None
                error = str(exc)
            duration_ms = (time.monotonic() - started) * 1000

            result_summary = (
                f"ERROR: {error}" if error else _summarize(tool_result)
            )
            record = ToolCallRecord(
                tool_name=tool.name,
                library=tool.library,
                arguments_redacted=self._redact(step.arguments),
                result_summary=result_summary,
                raw_result=tool_result,
                timestamp=datetime.now(UTC),
                duration_ms=round(duration_ms, 2),
            )
            result.tool_calls.append(record)
            self._emit(
                run_id, "tool_call", tool_name=tool.name,
                arguments_redacted=record.arguments_redacted,
                result_summary=result_summary,
                status="error" if error else "success",
            )

            # `arguments`/`tool_use_id` here (not just the display `content`
            # string) let a Converse-native provider rebuild its OWN prior
            # toolUse block verbatim on the next call -- see
            # llm.bedrock_provider._to_converse_messages. Real (unredacted)
            # arguments, since this is reconstructing what the model itself
            # already generated, not a new disclosure.
            conversation.append(
                {
                    "role": "assistant",
                    "content": f"Called {tool.name}({json.dumps(self._redact(step.arguments))})",
                    "tool_name": tool.name,
                    "arguments": step.arguments,
                    "tool_use_id": step.tool_use_id,
                }
            )
            # `content` here -- NOT `result_summary` -- is what a real model
            # actually sees in the next turn (see llm.bedrock_provider), so it
            # must carry the real tool output, not the 220-char trace preview;
            # a model reasoning over a truncated preview can't make correct
            # follow-up decisions (which sheet to inspect next, which columns
            # map to what). `result_summary` stays short -- it's only for the
            # traceability UI.
            conversation.append(
                {
                    "role": "user",
                    "content": f"Tool result: {_full_result_text(tool_result, error)}",
                    "structured": tool_result,
                    "tool_name": tool.name,
                    "error": error,
                    "tool_use_id": step.tool_use_id,
                }
            )

        result.status = "failed"
        result.completed_at = datetime.now(UTC)
        result.warnings.append(
            AgentWarning(code="max_iterations_exceeded",
                         message=f"Agent did not reach a final answer within {self.max_iterations} iterations.",
                         severity="critical")
        )
        self._emit(run_id, "agent_failed", status="error", message="max_iterations_exceeded")
        return result


def last_tool_result(result: AgentRunResult, tool_name: str) -> dict[str, Any] | None:
    """Returns the real, uncorrupted output of the most recent successful
    call to `tool_name`, straight from the actual Python tool execution --
    never whatever a model-driven provider claims in its own final text.
    A real model asked to retype a large structured tool result into its
    final answer risks truncating or mangling it; agents whose only real
    job is "call this one deterministic tool and report its output
    unchanged" (topic mapping, calculation planning) should prefer this
    over `result.output`."""
    for record in reversed(result.tool_calls):
        if record.tool_name == tool_name and not record.result_summary.startswith("ERROR:"):
            return record.raw_result
    return None


def _summarize(value: Any, max_len: int = 220) -> str:
    try:
        text = json.dumps(value, default=str)
    except TypeError:
        text = str(value)
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


# Cap well above _summarize's trace-display length (a real model needs the
# actual tool output to reason over) but still bounded, so one huge sheet
# dump can't blow the whole conversation's token budget. Empirically, a
# single detect_headings call on a real ~1700-block PBRER document alone
# serializes to ~18k chars -- a smaller cap silently truncates mid-JSON,
# handing the model an unparseable fragment it then can't faithfully copy
# into its next tool call (observed as the model dropping/mangling that
# argument entirely on every retry).
_MAX_CONVERSATION_RESULT_CHARS = 100_000


def _full_result_text(value: Any, error: str | None) -> str:
    if error:
        return f"ERROR: {error}"
    try:
        text = json.dumps(value, default=str)
    except TypeError:
        text = str(value)
    if len(text) <= _MAX_CONVERSATION_RESULT_CHARS:
        return text
    return text[:_MAX_CONVERSATION_RESULT_CHARS] + f"... [truncated, {len(text)} chars total]"
