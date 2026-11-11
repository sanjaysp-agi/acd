"""PBRER Section 16.3 Automation -- FastAPI entry point.

Serves the JSON API under /api and the buildless React frontend (web/) as
static files. No AWS/Bedrock configuration, credentials, or model IDs are
exposed here (prompt.md Part 7/8) -- same constraint the old Streamlit
app.py had.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from server.routers import comments, downloads, runs, topic_mapping, trace

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="PBRER Section 16.3 Automation")

# API routes must be registered before the catch-all static mount below --
# Starlette matches routes in registration order, so anything under /api
# needs to be seen first or the static mount would shadow it.
app.include_router(runs.router)
app.include_router(trace.router)
app.include_router(topic_mapping.router)
app.include_router(downloads.router)
app.include_router(comments.router)

app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
