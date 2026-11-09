"""Agent Execution & Traceability page: real tool invocations, never
simulated or fabricated. Reads the persisted JSONL trace for this run."""
from __future__ import annotations

import streamlit as st

from frontend.state import get_run_id, has_run
from observability.trace_store import TraceStore

_STATUS_ICON = {"success": "✅", "warning": "⚠️", "error": "🛑", "info": "ℹ️"}


def render():
    st.title("Agent Execution & Traceability")
    if not has_run():
        st.info("Run the pipeline first (Upload Documents).")
        return

    run_id = get_run_id()
    events = TraceStore().load_run(run_id)
    if not events:
        st.warning("No trace events recorded for this run.")
        return

    st.caption(f"{len(events)} real tool-invocation events recorded for run `{run_id}`. "
               "This is the agents' actual execution log, not a simulated timeline.")

    agents = sorted(set(e["agent_name"] for e in events))
    chosen_agents = st.multiselect("Filter by agent", agents, default=agents)

    for agent_name in agents:
        if agent_name not in chosen_agents:
            continue
        agent_events = [e for e in events if e["agent_name"] == agent_name]
        with st.expander(f"**{agent_name}** -- {len(agent_events)} events", expanded=False):
            for e in agent_events:
                icon = _STATUS_ICON.get(e.get("status", "info"), "")
                line = f"{icon} `{e['event_type']}`"
                if e.get("tool_name"):
                    line += f" -- **{e['tool_name']}**"
                st.write(line)
                if e.get("arguments_redacted"):
                    st.caption(f"args: {e['arguments_redacted']}")
                if e.get("result_summary"):
                    st.caption(f"result: {e['result_summary']}")
                if e.get("message"):
                    st.caption(e["message"])
