"""
Real tool-calling via the AWS Bedrock Converse API.

Honesty note (see README): local credential checks during development
(`aws bedrock list-foundation-models`) returned
`AccessDeniedException: ... make sure your API Key is valid` in both
eu-west-1 and us-east-1, using a validly-assumed SSO role
(AWSReservedSSO_PS_AIVAR_TEAM). Identity resolves fine
(`sts get-caller-identity` succeeds); Bedrock itself does not, which
reads as an access-gating issue (API-key/gateway layer or missing Bedrock
model-access grant) rather than a credentials problem this code can fix.
This provider is implemented against the documented Converse API tool-use
contract and unit-tested with a mocked client, but has NOT been exercised
against a live Bedrock endpoint in this environment. The application
defaults to LocalDeterministicProvider until Bedrock access is confirmed
working; do not claim Bedrock results are real when settings.llm.provider
is "bedrock" but the call fails -- surface the error, do not retry
silently, and do not fabricate a response.
"""
from __future__ import annotations

import json
from typing import Any

from config.settings import settings
from llm.cache import LLMCallCache
from llm.provider import AgentStep, ToolSpec


class BedrockInvocationError(RuntimeError):
    pass


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

            session = boto3.Session(profile_name=self.profile) if self.profile else boto3.Session()
            self._client = session.client("bedrock-runtime", region_name=self.region)
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
        messages = []
        for turn in conversation:
            role = turn.get("role", "user")
            text = turn.get("content", "")
            converse_role = "assistant" if role == "assistant" else "user"
            messages.append({"role": converse_role, "content": [{"text": str(text)}]})
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

        if self.cache is not None:
            cached = self.cache.get(self.model_id, system_prompt, conversation, tool_names)
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
            self.cache.put(self.model_id, system_prompt, conversation, tool_names, response)

        return self._parse_response(response)

    @staticmethod
    def _parse_response(response: dict[str, Any]) -> AgentStep:
        message = response.get("output", {}).get("message", {})
        content_blocks = message.get("content", [])
        for block in content_blocks:
            if "toolUse" in block:
                tu = block["toolUse"]
                return AgentStep(type="call_tool", tool_name=tu["name"], arguments=tu.get("input", {}) or {})
        # No tool use block -> treat as final; the agent must still parse
        # structured JSON out of the text content itself.
        text_parts = [b.get("text", "") for b in content_blocks if "text" in b]
        text = "\n".join(text_parts)
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            parsed = {"raw_text": text}
        return AgentStep(type="final", final_output=parsed)
