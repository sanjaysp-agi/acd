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

# Bump whenever a detector/extraction code path changes in a way that
# would make a previously-cached analysis stale even though the SOURCE
# FILE's bytes didn't change. History:
#   v2: tried a text-alignment table-detection fallback for borderless
#       PDF tables in _load_pdf_blocks -- reverted (see that function's
#       docstring) after it was found, against a real PBRER PDF, to
#       misclassify a heading line as part of a false "table", regressing
#       section detection. Superseded by v3; no code depends on v2 shape.
#   v3: tools.document_tools._numbered_heading_headings gained a quality
#       filter (_looks_like_real_heading) rejecting PDF line-wrap
#       fragments that merely start with a digit (dosage figures,
#       footnote/date citations, leaked table-row numbers) from being
#       misdetected as section headings -- a PDF analyzed under v1/v2
#       could have the wrong heading list entirely.
CONFIG_VERSION = "v3"


def _cache_key(model_id: str, system_prompt: str, conversation: list[dict[str, Any]], tool_names: list[str],
                generation_config: dict[str, Any]) -> str:
    payload = {
        "model_id": model_id,
        "system_prompt": system_prompt,
        "conversation": conversation,
        "tool_names": sorted(tool_names),
        # Generation params that change the actual response (e.g.
        # max_output_tokens truncating mid-tool-call) MUST be in the key --
        # otherwise changing one after a broken call is cached silently
        # keeps serving the old, broken response forever.
        "generation_config": generation_config,
        "config_version": CONFIG_VERSION,
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class LLMCallCache:
    def __init__(self, cache_dir: Path = CACHE_DIR / "llm_calls"):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, model_id: str, system_prompt: str, conversation: list[dict[str, Any]],
            tool_names: list[str], generation_config: dict[str, Any] | None = None) -> dict[str, Any] | None:
        key = _cache_key(model_id, system_prompt, conversation, tool_names, generation_config or {})
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def put(self, model_id: str, system_prompt: str, conversation: list[dict[str, Any]],
             tool_names: list[str], result: dict[str, Any], generation_config: dict[str, Any] | None = None) -> None:
        key = _cache_key(model_id, system_prompt, conversation, tool_names, generation_config or {})
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


class AnalysisCache:
    """File-hash-keyed cache for a whole agent analysis result (prompt.md
    Part 8 cost-control item 6). Keyed on content hash + CONFIG_VERSION, so
    re-running the app against byte-identical inputs skips the agent's
    tool-calling loop (and every LLM call it would have made) entirely,
    rather than only de-duplicating individual LLM calls. Any change to
    the file's bytes, or a bump of CONFIG_VERSION after a detector/prompt
    change, invalidates the cache automatically."""

    def __init__(self, cache_dir: Path = CACHE_DIR / "analysis"):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, kind: str, file_path: str | Path) -> Path:
        key = f"{kind}_{file_hash(file_path)}_{CONFIG_VERSION}"
        return self.cache_dir / f"{key}.json"

    def get(self, kind: str, file_path: str | Path) -> dict[str, Any] | None:
        path = self._path(kind, file_path)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def put(self, kind: str, file_path: str | Path, result: dict[str, Any]) -> None:
        path = self._path(kind, file_path)
        path.write_text(json.dumps(result, default=str), encoding="utf-8")
