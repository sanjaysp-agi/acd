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
                conversation.append({"role": "assistant", "content": f"[invalid tool request: {step.tool_name}]"})
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
                raw_result=tool_result if isinstance(tool_result, dict) else {"value": tool_result},
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

            conversation.append(
                {
                    "role": "assistant",
                    "content": f"Called {tool.name}({json.dumps(self._redact(step.arguments))})",
                }
            )
            conversation.append(
                {
                    "role": "user",
                    "content": f"Tool result: {result_summary}",
                    "structured": tool_result,
                    "tool_name": tool.name,
                    "error": error,
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


def _summarize(value: Any, max_len: int = 220) -> str:
    try:
        text = json.dumps(value, default=str)
    except TypeError:
        text = str(value)
    return text if len(text) <= max_len else text[: max_len - 3] + "..."
