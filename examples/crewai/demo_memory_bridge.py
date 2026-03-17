#!/usr/bin/env python3
"""Demo 1 — The Memory Bridge.

Three independent CrewAI crew runs across a simulated day. Without Statis,
each run starts fresh. With Statis, each run picks up where the last left off.

This proves *continuity* — POST /events persists facts that survive across
separate crew executions.

Usage:
    python demo_memory_bridge.py
    python demo_memory_bridge.py --reprovision
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone

import httpx
from crewai import Agent, Crew, Process, Task

from provision import provision, get_key, CACHE_FILE
from statis_tools import make_push_tool, make_read_tool, make_history_tool


ENTITY_TYPE = "account"
ENTITY_ID = f"acct-bridge-{uuid.uuid4().hex[:6]}"


def _print_header(text: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")


def _print_state(base_url: str, master_key: str) -> None:
    r = httpx.get(
        f"{base_url}/state/{ENTITY_TYPE}/{ENTITY_ID}",
        headers={"X-API-Key": master_key},
        timeout=10,
        verify=False,
    )
    if r.status_code == 200:
        data = r.json()
        s = data.get("state", {})
        print(f"  state_version: {data['state_version']}")
        print(f"  state_hash:    {data.get('state_hash', 'n/a')[:24]}...")
        for k, v in s.items():
            print(f"  {k:16s}: {v}")
    elif r.status_code == 404:
        print("  (no state yet)")
    print()


def run_morning_crew(manifest: dict, base_url: str) -> None:
    """Run 1: Triage agent classifies a ticket."""
    _print_header("RUN 1: MORNING CREW — Triage")

    triage = Agent(
        role="Morning Triage Specialist",
        goal=(
            f"Classify the incoming ticket and publish a support.incident_reported "
            f"event to Statis for entity {ENTITY_TYPE}/{ENTITY_ID}."
        ),
        backstory="You are the morning shift triage engineer.",
        tools=[make_push_tool(get_key(manifest, "crewai_triage"), base_url)],
        verbose=True,
    )

    task = Task(
        description=(
            f"A new support ticket arrived: 'Login page returning 500 errors, "
            f"200+ users affected, started 10 minutes ago.'\n\n"
            f"Publish a support.incident_reported event using statis_push_event:\n"
            f"  entity_type: {ENTITY_TYPE}\n"
            f"  entity_id: {ENTITY_ID}\n"
            f"  event_type: support.incident_reported\n"
            f"  payload: incident_id, type=outage, status=open, severity=high, summary\n"
            f"  producer: crewai_triage"
        ),
        expected_output="Confirmation the incident event was published.",
        agent=triage,
    )

    crew = Crew(agents=[triage], tasks=[task], process=Process.sequential, verbose=True)
    crew.kickoff()

    print("\n📊 State after Run 1:")
    _print_state(base_url, manifest["master_key"])


def run_midday_crew(manifest: dict, base_url: str) -> None:
    """Run 2: Sentiment agent reads Run 1's state** and adds analysis."""
    _print_header("RUN 2: MIDDAY CREW — Sentiment Analysis")

    sentiment = Agent(
        role="Midday Sentiment Analyst",
        goal=(
            f"Read the current state for {ENTITY_TYPE}/{ENTITY_ID}, then "
            f"publish a support.sentiment_updated event based on this angry "
            f"customer email."
        ),
        backstory=(
            "You are the midday analyst. You always read the current entity "
            "state first to understand context before analyzing sentiment."
        ),
        tools=[
            make_read_tool(get_key(manifest, "crewai_sentiment"), base_url),
            make_push_tool(get_key(manifest, "crewai_sentiment"), base_url),
        ],
        verbose=True,
    )

    task = Task(
        description=(
            f"First, read the current state for {ENTITY_TYPE}/{ENTITY_ID} "
            f"using statis_read_state to see what happened in the morning.\n\n"
            f"Then analyze this email: 'This is unacceptable. Third outage "
            f"this quarter. We are evaluating alternatives.'\n\n"
            f"Publish a support.sentiment_updated event:\n"
            f"  entity_type: {ENTITY_TYPE}\n"
            f"  entity_id: {ENTITY_ID}\n"
            f"  event_type: support.sentiment_updated\n"
            f"  payload: label=negative\n"
            f"  producer: crewai_sentiment"
        ),
        expected_output=(
            "What you saw in the morning state + confirmation that sentiment "
            "was published. Prove that you read the conitnuity from Run 1."
        ),
        agent=sentiment,
    )

    crew = Crew(agents=[sentiment], tasks=[task], process=Process.sequential, verbose=True)
    crew.kickoff()

    print("\n📊 State after Run 2 (morning + midday combined):")
    _print_state(base_url, manifest["master_key"])


def run_evening_crew(manifest: dict, base_url: str) -> None:
    """Run 3: CSM reads the full day's state and decides action."""
    _print_header("RUN 3: EVENING CREW — CSM Decision")

    csm = Agent(
        role="Evening CSM",
        goal=(
            f"Read the full state for {ENTITY_TYPE}/{ENTITY_ID} — which now "
            f"contains the morning incident AND midday sentiment — and decide "
            f"whether to escalate."
        ),
        backstory=(
            "You are the evening CSM. You read the golden record to see the "
            "ENTIRE day's activity before making your decision."
        ),
        tools=[
            make_read_tool(get_key(manifest, "crewai_csm"), base_url),
            make_push_tool(get_key(manifest, "crewai_csm"), base_url),
            make_history_tool(get_key(manifest, "crewai_csm"), base_url),
        ],
        verbose=True,
    )

    task = Task(
        description=(
            f"1. Read the current state for {ENTITY_TYPE}/{ENTITY_ID} using "
            f"statis_read_state.\n"
            f"2. Read the event timeline using statis_read_history.\n"
            f"3. Based on the FULL day's picture (incident + sentiment), "
            f"publish a csm.escalation_requested event:\n"
            f"   entity_type: {ENTITY_TYPE}\n"
            f"   entity_id: {ENTITY_ID}\n"
            f"   event_type: csm.escalation_requested\n"
            f"   payload: owner=sales, action=pause outreach, reason=churn risk\n"
            f"   producer: crewai_csm\n\n"
            f"Prove that you can see events from ALL three runs."
        ),
        expected_output=(
            "The full state you read (showing morning + midday data), the "
            "event history, and confirmation of your escalation decision."
        ),
        agent=csm,
    )

    crew = Crew(agents=[csm], tasks=[task], process=Process.sequential, verbose=True)
    crew.kickoff()

    print("\n📊 Final state after all 3 runs:")
    _print_state(base_url, manifest["master_key"])


def main() -> None:
    if "--reprovision" in sys.argv and CACHE_FILE.exists():
        CACHE_FILE.unlink()

    _print_header("DEMO 1: THE MEMORY BRIDGE")
    print("Three independent CrewAI runs, one shared golden record.\n")

    manifest = provision()
    base_url = manifest.get("base_url", "http://localhost:8000")

    print(f"Entity: {ENTITY_TYPE}/{ENTITY_ID}\n")

    run_morning_crew(manifest, base_url)
    run_midday_crew(manifest, base_url)
    run_evening_crew(manifest, base_url)

    _print_header("MEMORY BRIDGE COMPLETE")
    print("  The evening CSM saw the ENTIRE day's context — incidents,")
    print("  sentiment, timeline — even though each crew run was independent.")
    print()
    print("  Without Statis, each run starts from scratch. With Statis,")
    print("  every fact persists and the golden record grows.")
    print()


if __name__ == "__main__":
    main()
