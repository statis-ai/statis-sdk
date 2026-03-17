"""Statis tools for CrewAI agents.

Four BaseTool subclasses wrapping the Statis API. Each tool is instantiated
with a per-agent ``api_key`` so that identity, RBAC, and audit trail work
automatically.

Usage:
    push = StatisPushEvent(api_key="st_...", base_url="http://localhost:8000")
    read = StatisReadState(api_key="st_...", base_url="http://localhost:8000")
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Type

import httpx
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


DEFAULT_BASE_URL = os.getenv("STATIS_API_URL", "http://localhost:8000")


# ── Schemas ──────────────────────────────────────────────────────────

class PushEventInput(BaseModel):
    """Input schema for StatisPushEvent."""
    entity_type: str = Field(description="Entity type, e.g. 'account'")
    entity_id: str = Field(description="Entity ID, e.g. 'acct-42'")
    event_type: str = Field(description="Semantic event type, e.g. 'support.incident_reported'")
    payload: str = Field(description="Event payload as a JSON string, e.g. '{\"severity\": \"high\", \"summary\": \"outage\"}'")
    producer: str = Field(default="crewai", description="Producer name")


class ReadStateInput(BaseModel):
    """Input schema for StatisReadState."""
    entity_type: str = Field(description="Entity type, e.g. 'account'")
    entity_id: str = Field(description="Entity ID, e.g. 'acct-42'")


class ReadHistoryInput(BaseModel):
    """Input schema for StatisReadHistory."""
    entity_type: str = Field(description="Entity type")
    entity_id: str = Field(description="Entity ID")
    limit: int = Field(default=20, description="Max events to return")


class TimeTravelInput(BaseModel):
    """Input schema for StatisTimeTravel."""
    entity_type: str = Field(description="Entity type")
    entity_id: str = Field(description="Entity ID")
    rev: int = Field(description="Revision number to inspect")


# ── Tools ────────────────────────────────────────────────────────────

class StatisPushEvent(BaseTool):
    """Publish a semantic event to the Statis event bus."""
    name: str = "statis_push_event"
    description: str = (
        "Publish a semantic event to Statis. Use this to record facts, signals, "
        "or decisions so other agents and systems can see them. "
        "Provide entity_type, entity_id, event_type, and a payload dict."
    )
    args_schema: Type[BaseModel] = PushEventInput

    api_key: str = ""
    base_url: str = DEFAULT_BASE_URL
    trace_id: Optional[str] = None

    def _run(
        self,
        entity_type: str,
        entity_id: str,
        event_type: str,
        payload: str,
        producer: str = "crewai",
    ) -> str:
        # Parse payload from JSON string
        try:
            payload_dict = json.loads(payload) if isinstance(payload, str) else payload
        except json.JSONDecodeError:
            return f"❌ Invalid JSON in payload: {payload}"

        event_id = f"crew_{uuid.uuid4().hex[:12]}"
        body = {
            "event_id": event_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "event_type": event_type,
            "payload": payload_dict,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "producer": producer,
            "schema_version": "1",
        }
        if self.trace_id:
            body["trace_id"] = self.trace_id

        r = httpx.post(
            f"{self.base_url}/events",
            json=body,
            headers={"X-API-Key": self.api_key},
            timeout=10,
            verify=False,
        )
        if r.status_code in (200, 201):
            return f"✅ Event published: {event_type} (id={event_id})"
        return f"❌ Failed to publish event: HTTP {r.status_code} — {r.text}"


class StatisReadState(BaseTool):
    """Read the current materialized entity state from Statis."""
    name: str = "statis_read_state"
    description: str = (
        "Read the current golden state for an entity from Statis. "
        "Returns the full materialized state, version, hash, and provenance. "
        "RBAC may redact fields based on your API key's role."
    )
    args_schema: Type[BaseModel] = ReadStateInput

    api_key: str = ""
    base_url: str = DEFAULT_BASE_URL

    def _run(self, entity_type: str, entity_id: str) -> str:
        r = httpx.get(
            f"{self.base_url}/state/{entity_type}/{entity_id}",
            headers={"X-API-Key": self.api_key},
            timeout=10,
            verify=False,
        )
        if r.status_code == 404:
            return "No state found for this entity yet."
        if r.status_code != 200:
            return f"❌ Failed to read state: HTTP {r.status_code} — {r.text}"
        data = r.json()
        return json.dumps(data, indent=2)


class StatisReadHistory(BaseTool):
    """Read the event timeline for an entity from Statis."""
    name: str = "statis_read_history"
    description: str = (
        "Read the event history/timeline for an entity. "
        "Returns a list of events showing what happened over time."
    )
    args_schema: Type[BaseModel] = ReadHistoryInput

    api_key: str = ""
    base_url: str = DEFAULT_BASE_URL

    def _run(self, entity_type: str, entity_id: str, limit: int = 20) -> str:
        r = httpx.get(
            f"{self.base_url}/events",
            params={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "limit": limit,
            },
            headers={"X-API-Key": self.api_key},
            timeout=10,
            verify=False,
        )
        if r.status_code != 200:
            return f"❌ Failed to read history: HTTP {r.status_code} — {r.text}"
        events = r.json()
        if not events:
            return "No events found for this entity."
        return json.dumps(events, indent=2)


class StatisTimeTravel(BaseTool):
    """Read entity state at a specific revision (time travel)."""
    name: str = "statis_time_travel"
    description: str = (
        "Read what the entity state looked like at a specific revision number. "
        "Use this for audit: 'What did agent X know at rev N?'"
    )
    args_schema: Type[BaseModel] = TimeTravelInput

    api_key: str = ""
    base_url: str = DEFAULT_BASE_URL

    def _run(self, entity_type: str, entity_id: str, rev: int) -> str:
        r = httpx.get(
            f"{self.base_url}/state/{entity_type}/{entity_id}/at",
            params={"rev": rev},
            headers={"X-API-Key": self.api_key},
            timeout=10,
            verify=False,
        )
        if r.status_code == 404:
            return f"No state found at revision {rev}."
        if r.status_code != 200:
            return f"❌ Failed: HTTP {r.status_code} — {r.text}"
        data = r.json()
        return json.dumps(data, indent=2)


# ── Factory helpers ──────────────────────────────────────────────────

def make_push_tool(api_key: str, base_url: str = DEFAULT_BASE_URL, trace_id: str | None = None) -> StatisPushEvent:
    return StatisPushEvent(api_key=api_key, base_url=base_url, trace_id=trace_id)

def make_read_tool(api_key: str, base_url: str = DEFAULT_BASE_URL) -> StatisReadState:
    return StatisReadState(api_key=api_key, base_url=base_url)

def make_history_tool(api_key: str, base_url: str = DEFAULT_BASE_URL) -> StatisReadHistory:
    return StatisReadHistory(api_key=api_key, base_url=base_url)

def make_time_travel_tool(api_key: str, base_url: str = DEFAULT_BASE_URL) -> StatisTimeTravel:
    return StatisTimeTravel(api_key=api_key, base_url=base_url)
