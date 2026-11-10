"""
Real tool-calling via the AWS Bedrock Converse API.

Verified end-to-end against a live Bedrock endpoint (account 154012156735,
role AWSReservedSSO_PS_EPD_AIML_WR_TEAM, eu-west-1) with
PBRER_LLM_PROVIDER=bedrock -- Document Agent, Excel Agent, Topic Mapping
Agent, and Calculation Planning Agent all produced correct results
(reproducing the same figures as local-deterministic mode against the
real fixtures). Three real, non-obvious issues had to be fixed to get
there, beyond simply calling the API:
  1. The conversation history sent to the model must use genuine Converse
     toolUse/toolResult content blocks (see _to_converse_messages), not
     flattened text -- the model has no reliable memory of its own prior
     tool-call arguments otherwise.
  2. max_output_tokens must be generous (settings.llm.max_output_tokens,
     16000 by default) -- the model frequently needs to echo a prior tool
     result's array back as the next call's argument, and a too-small
     budget truncates that generation silently with no error raised.
  3. Document/Excel/Topic-Mapping/Calculation-Planning agents never trust
     this provider's own free-form final text for the actual structured
     result (observed coming back wrapped in markdown fences, with
     drifted field names); each agent instead assembles its real output
     from `AgentRunResult.tool_calls` -- the actual, deterministic Python
     tool executions -- using `agents.base.last_tool_result` or the
     per-agent `_assemble_*` helpers. The model's only real job is
     deciding which tool to call next and with what arguments.
Local-deterministic mode remains the default (PBRER_LLM_PROVIDER=local);
do not claim Bedrock results are real when a call fails -- surface the
error, do not retry silently, and do not fabricate a response.
"""
from __future__ import annotations

import json
from typing import Any

from config.settings import settings
from llm.cache import LLMCallCache
from llm.provider import AgentStep, ToolSpec


class BedrockInvocationError(RuntimeError):
    pass


# Mirrors agents.base._MAX_CONVERSATION_RESULT_CHARS/_full_result_text --
# duplicated locally rather than imported so llm/ doesn't depend on
# agents/ (the dependency runs the other way).
_MAX_TOOL_RESULT_TEXT_CHARS = 100_000


def _full_result_text(value: Any) -> str:
    try:
        text = json.dumps(value, default=str)
    except TypeError:
        text = str(value)
    if len(text) <= _MAX_TOOL_RESULT_TEXT_CHARS:
        return text
    return text[:_MAX_TOOL_RESULT_TEXT_CHARS] + f"... [truncated, {len(text)} chars total]"


class BedrockProvider:
    mode = "bedrock"

    def __init__(self, model_id: str | None = None, region: str | None = None,
                 profile: str | None = None, max_output_tokens: int | None = None,
                 cache: LLMCallCache | None = None):
        self.model_id = model_id or settings.llm.bedrock_model_id
        self.region = region or settings.llm.aws_region
        self.profile = profile or settings.llm.aws_profile
        self.max_output_tokens = max_output_tokens or settings.llm.max_output_tokens
        self.cache = cache if cache is not None else (LLMCallCache() if settings.llm.enable_cache else None)
        self.invocation_count = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3
            from botocore.config import Config

            # botocore's default read_timeout (~60s) is too short once the
            # conversation/output genuinely needs it (a real multi-thousand-
            # token generation, or a large tool-result payload in the
            # request) -- confirmed empirically via a live ReadTimeoutError
            # well before the model had finished responding.
            config = Config(read_timeout=300, connect_timeout=10, retries={"max_attempts": 2})
            session = boto3.Session(profile_name=self.profile) if self.profile else boto3.Session()
            self._client = session.client("bedrock-runtime", region_name=self.region, config=config)
        return self._client

    @staticmethod
    def _tool_config(tools: list[ToolSpec]) -> dict[str, Any]:
        return {
            "tools": [
                {
                    "toolSpec": {
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": {"json": t.parameters_schema},
                    }
                }
                for t in tools
            ]
        }

    @staticmethod
    def _to_converse_messages(conversation: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Rebuilds genuine Converse toolUse/toolResult content blocks from
        the conversation instead of flattening everything to plain text.
        Converse's tool-use protocol expects an assistant toolUse block to
        be answered by a user toolResult block carrying the SAME
        toolUseId; without that native structure the model has no reliable
        signal that it previously generated a specific tool call with
        specific arguments, and was observed (empirically, against a live
        endpoint) to silently drop large arguments on the next turn when
        conversation history was just plain text instead."""
        messages = []
        for turn in conversation:
            role = turn.get("role", "user")
            converse_role = "assistant" if role == "assistant" else "user"
            tool_use_id = turn.get("tool_use_id")

            if tool_use_id and converse_role == "assistant" and "arguments" in turn:
                messages.append({
                    "role": "assistant",
                    "content": [{"toolUse": {"toolUseId": tool_use_id, "name": turn.get("tool_name"),
                                              "input": turn.get("arguments") or {}}}],
                })
                continue

            if tool_use_id and converse_role == "user" and "tool_name" in turn and "arguments" not in turn:
                error = turn.get("error")
                structured = turn.get("structured")
                # Converse's toolResult "json" content block requires a
                # JSON OBJECT -- rejects a bare array (ValidationException),
                # and several of this app's tools (e.g.
                # reconstruct_section_numbers) return a top-level list. Use
                # "text" uniformly instead of branching on type; the model
                # parses JSON out of text fine either way.
                content_block = {"text": error if error else _full_result_text(structured)}
                messages.append({
                    "role": "user",
                    "content": [{"toolResult": {
                        "toolUseId": tool_use_id,
                        "content": [content_block],
                        "status": "error" if error else "success",
                    }}],
                })
                continue

            messages.append({"role": converse_role, "content": [{"text": str(turn.get("content", ""))}]})

        if not messages:
            messages.append({"role": "user", "content": [{"text": "Begin."}]})
        return messages

    def decide(self, system_prompt: str, conversation: list[dict[str, Any]], tools: list[ToolSpec]) -> AgentStep:
        if settings.llm.max_invocations_per_run and self.invocation_count >= settings.llm.max_invocations_per_run:
            raise BedrockInvocationError(
                f"Max Bedrock invocations per run ({settings.llm.max_invocations_per_run}) exceeded."
            )

        messages = self._to_converse_messages(conversation)
        tool_names = [t.name for t in tools]
        generation_config = {"max_output_tokens": self.max_output_tokens, "temperature": settings.llm.temperature}

        if self.cache is not None:
            cached = self.cache.get(self.model_id, system_prompt, conversation, tool_names, generation_config)
            if cached is not None:
                return self._parse_response(cached)

        client = self._get_client()
        try:
            response = client.converse(
                modelId=self.model_id,
                system=[{"text": system_prompt}],
                messages=messages,
                toolConfig=self._tool_config(tools),
                inferenceConfig={"maxTokens": self.max_output_tokens, "temperature": settings.llm.temperature},
            )
        except Exception as exc:  # noqa: BLE001 -- surfaced to caller, never swallowed/retried silently
            raise BedrockInvocationError(f"Bedrock Converse call failed: {exc}") from exc

        self.invocation_count += 1
        usage = response.get("usage", {})
        self.total_input_tokens += usage.get("inputTokens", 0)
        self.total_output_tokens += usage.get("outputTokens", 0)

        if self.cache is not None:
            self.cache.put(self.model_id, system_prompt, conversation, tool_names, response, generation_config)

        return self._parse_response(response)

    @staticmethod
    def _parse_response(response: dict[str, Any]) -> AgentStep:
        message = response.get("output", {}).get("message", {})
        content_blocks = message.get("content", [])
        for block in content_blocks:
            if "toolUse" in block:
                tu = block["toolUse"]
                return AgentStep(type="call_tool", tool_name=tu["name"], arguments=tu.get("input", {}) or {},
                                  tool_use_id=tu.get("toolUseId"))
        # No tool use block -> treat as final; the agent must still parse
        # structured JSON out of the text content itself.
        text_parts = [b.get("text", "") for b in content_blocks if "text" in b]
        text = "\n".join(text_parts)
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            parsed = {"raw_text": text}
        return AgentStep(type="final", final_output=parsed)
