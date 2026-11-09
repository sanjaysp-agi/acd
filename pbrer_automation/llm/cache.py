"""
Hash-based cache for LLM calls, keyed on (model_id, system_prompt,
conversation, tool names, config version) so identical reasoning steps
are never re-sent to Bedrock. Cost-control requirement from prompt.md
Part 8: avoid repeating identical model calls.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from config.settings import CACHE_DIR

CONFIG_VERSION = "v1"


def _cache_key(model_id: str, system_prompt: str, conversation: list[dict[str, Any]], tool_names: list[str]) -> str:
    payload = {
        "model_id": model_id,
        "system_prompt": system_prompt,
        "conversation": conversation,
        "tool_names": sorted(tool_names),
        "config_version": CONFIG_VERSION,
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class LLMCallCache:
    def __init__(self, cache_dir: Path = CACHE_DIR / "llm_calls"):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, model_id: str, system_prompt: str, conversation: list[dict[str, Any]],
            tool_names: list[str]) -> dict[str, Any] | None:
        key = _cache_key(model_id, system_prompt, conversation, tool_names)
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def put(self, model_id: str, system_prompt: str, conversation: list[dict[str, Any]],
             tool_names: list[str], result: dict[str, Any]) -> None:
        key = _cache_key(model_id, system_prompt, conversation, tool_names)
        path = self.cache_dir / f"{key}.json"
        path.write_text(json.dumps(result, default=str), encoding="utf-8")


def file_hash(file_path: str | Path) -> str:
    """Stable content hash for a source file, used to cache document/workbook
    analysis so re-running the app on the same inputs doesn't redo work."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
