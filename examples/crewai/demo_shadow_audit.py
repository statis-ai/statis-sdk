#!/usr/bin/env python3
"""Demo 4 — Shadow Audit.

A "Junior" crew (cheaper LLM) processes events. A "Senior Auditor" agent
(stronger LLM) uses Statis time-travel to review the junior's work,
walking through each revision and flagging suspicious state transitions.

Usage:
    python demo_shadow_audit.py
    python demo_shadow_audit.py --reprovision
"""
from __future__ import annotations

import json
import sys
import uuid

import httpx
from crewai import Agent, Crew, Process, Task

from provision import provision, get_key, CACHE_FILE
from statis_tools import (
    make_push_tool,
    make_read_tool,
    make_history_tool,
    make_time_travel_tool,
)


ENTITY_TYPE = "account"
ENTITY_ID = f"acct-audit-{uuid.uuid4().hex[:6]}"


def _print_header(text: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")


def _print_state(base_url: str, master_key: str) -> None:
    r = httpx.get(
        f"{base_url}/state/{ENTITY_TYPE}/{ENTITY_ID}",
        headers={"X-API-Key": master_key},
        timeout=10,
    )
    if r.status_code == 200:
        data = r.json()
        s = data.get("state", {})
        print(f"  state_version: {data['state_version']}")
        for k, v in s.items():
            print(f"  {k:16s}: {v}")
    print()


def run_junior_crew(manifest: dict, base_url: str) -> None:
    """Phase 1: Junior agents process the scenario (simulated cheaper LLM)."""
    _print_header("PHASE 1: JUNIOR CREW PROCESSING")

    triage = Agent(
        role="Junior Triage Agent",
        goal=(
            f"Classify the support ticket and publish a support.incident_reported "
            f"event for {ENTITY_TYPE}/{ENTITY_ID}."
        ),
        backstory="You are a junior support engineer, sometimes you rush.",
        tools=[make_push_tool(get_key(manifest, "crewai_triage"), base_url)],
        verbose=True,
    )

    sentiment = Agent(
        role="Junior Sentiment Agent",
        goal=(
            f"Analyze the customer email and publish a support.sentiment_updated "
            f"event for {ENTITY_TYPE}/{ENTITY_ID}."
        ),
        backstory="You are a junior sentiment analyst, still learning nuance.",
        tools=[make_push_tool(get_key(manifest, "crewai_sentiment"), base_url)],
        verbose=True,
    )

    triage_task = Task(
        description=(
            f"Classify this ticket: 'Our API returns 504 timeouts intermittently. "
            f"Not all users affected, maybe 10% seeing errors.'\n\n"
            f"Use statis_push_event:\n"
            f"  entity_type: {ENTITY_TYPE}, entity_id: {ENTITY_ID}\n"
            f"  event_type: support.incident_reported\n"
            f"  payload: incident_id, type, status, severity, summary\n"
            f"  producer: crewai_triage"
        ),
        expected_output="Confirmation of the published event.",
        agent=triage,
    )

    sentiment_task = Task(
        description=(
            f"Analyze this email: 'Hey, we noticed some slowness in the API "
            f"today. Not a big deal, just wanted to flag it. Keep up the "
            f"great work!'\n\n"
            f"Use statis_push_event:\n"
            f"  entity_type: {ENTITY_TYPE}, entity_id: {ENTITY_ID}\n"
            f"  event_type: support.sentiment_updated\n"
            f"  payload: label (positive/neutral/negative)\n"
            f"  producer: crewai_sentiment"
        ),
        expected_output="Confirmation of the published sentiment event.",
        agent=sentiment,
    )

    crew = Crew(
        agents=[triage, sentiment],
        tasks=[triage_task, sentiment_task],
        process=Process.sequential,
        verbose=True,
    )
    crew.kickoff()

    print("\n📊 State after Junior Crew:")
    _print_state(base_url, manifest["master_key"])


def run_senior_auditor(manifest: dict, base_url: str) -> None:
    """Phase 2: Senior agent reviews each revision via time-travel."""
    _print_header("PHASE 2: SENIOR AUDITOR REVIEW")

    # First, get the current state version so the auditor knows
    # how many revisions to review
    r = httpx.get(
        f"{base_url}/state/{ENTITY_TYPE}/{ENTITY_ID}",
        headers={"X-API-Key": manifest["master_key"]},
        timeout=10,
        verify=False,
    )
    if r.status_code != 200:
        print("  ⚠ Could not read state for audit.")
        return

    final_version = r.json().get("state_version", 1)

    auditor = Agent(
        role="Senior Governance Auditor",
        goal=(
            f"Audit the junior crew's work on {ENTITY_TYPE}/{ENTITY_ID}. "
            f"Walk through each revision (1 to {final_version}) using time "
            f"travel, read the event history, and flag any suspicious state "
            f"transitions or inconsistencies."
        ),
        backstory=(
            "You are a senior governance auditor with deep experience. You "
            "use Statis time-travel to walk through each state revision the "
            "junior agents produced. You compare event payloads against "
            "materialized state and flag inconsistencies. You are thorough "
            "and detail-oriented."
        ),
        tools=[
            make_read_tool(manifest["master_key"], base_url),
            make_history_tool(manifest["master_key"], base_url),
            make_time_travel_tool(manifest["master_key"], base_url),
        ],
        verbose=True,
    )

    audit_task = Task(
        description=(
            f"Audit the state transitions for {ENTITY_TYPE}/{ENTITY_ID}.\n\n"
            f"1. Read the event history using statis_read_history\n"
            f"2. For each revision (1 to {final_version}), use statis_time_travel "
            f"   to inspect the state at that point\n"
            f"3. Compare each event's payload against the resulting state\n"
            f"4. Flag any inconsistencies — for example, if sentiment was "
            f"   classified as 'positive' but the original email context "
            f"   suggests otherwise\n"
            f"5. Produce a governance audit report with your findings\n\n"
            f"Be specific: cite event IDs, revision numbers, and exact "
            f"field values in your findings."
        ),
        expected_output=(
            "A governance audit report listing:\n"
            "- Each revision reviewed and its state\n"
            "- Any inconsistencies or suspicious transitions\n"
            "- Overall assessment: PASS or FLAG for review"
        ),
        agent=auditor,
    )

    crew = Crew(
        agents=[auditor],
        tasks=[audit_task],
        process=Process.sequential,
        verbose=True,
    )
    result = crew.kickoff()

    _print_header("AUDIT REPORT")
    print(result)


def main() -> None:
    if "--reprovision" in sys.argv and CACHE_FILE.exists():
        CACHE_FILE.unlink()

    _print_header("DEMO 4: SHADOW AUDIT")
    print("Junior crew processes events → Senior auditor reviews via time travel.\n")

    manifest = provision()
    base_url = manifest.get("base_url", "http://localhost:8000")

    print(f"Entity: {ENTITY_TYPE}/{ENTITY_ID}\n")

    run_junior_crew(manifest, base_url)
    run_senior_auditor(manifest, base_url)

    _print_header("SHADOW AUDIT COMPLETE")
    print("  The Senior Auditor used Statis time-travel to inspect every")
    print("  revision the Junior Crew produced — proving that Statis isn't")
    print("  just for coordination, it's for trust and verification.")
    print()


if __name__ == "__main__":
    main()
