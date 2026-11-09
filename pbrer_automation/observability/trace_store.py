"""
Persisted structured execution events, keyed by run ID. This is what
feeds the frontend's "Agent Execution & Traceability" page -- every
event is a REAL tool invocation recorded by agents.base.ToolCallingAgent,
never a fabricated/simulated log line.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from config.settings import RUNS_DIR


class TraceStore:
    def __init__(self, runs_dir: Path = RUNS_DIR):
        self.runs_dir = runs_dir
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _run_path(self, run_id: str) -> Path:
        return self.runs_dir / f"{run_id}.jsonl"

    def make_sink(self, run_id: str):
        """Returns a callable suitable as agents.base.ToolCallingAgent's
        trace_sink -- appends one JSON line per event, thread-safe."""
        path = self._run_path(run_id)

        def sink(event: dict[str, Any]) -> None:
            record = dict(event)
            if isinstance(record.get("timestamp"), datetime):
                record["timestamp"] = record["timestamp"].isoformat()
            line = json.dumps(record, default=str)
            with self._lock:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")

        return sink

    def load_run(self, run_id: str) -> list[dict[str, Any]]:
        path = self._run_path(run_id)
        if not path.exists():
            return []
        events = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return events

    def list_runs(self) -> list[str]:
        return sorted(p.stem for p in self.runs_dir.glob("*.jsonl"))
