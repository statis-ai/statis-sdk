#!/usr/bin/env python3
"""Demo 3 — Multi-Crew Pipeline.

Three independent teams — Support, Account Management, Revenue — each run
their own CrewAI crews. Statis is the "Brain Stem" connecting them.

When Support's crew detects a crisis, it publishes events to Statis.
Statis subscriptions fire webhooks that trigger the Account and Revenue crews.

Prerequisites:
    1. Start the Statis API
    2. Start the webhook receiver:  python webhook_crew_trigger.py
    3. Start the worker:  cd worker && python main.py
    4. Run this script:  python demo_multi_crew.py

Usage:
    python demo_multi_crew.py
    python demo_multi_crew.py --reprovision
"""
from __future__ import annotations

import json
import sys
import time
import uuid

import httpx
from crewai import Agent, Crew, Process, Task

from provision import provision, get_key, CACHE_FILE
from statis_tools import make_push_tool, make_read_tool


ENTITY_TYPE = "account"
ENTITY_ID = f"acct-multi-{uuid.uuid4().hex[:6]}"
WEBHOOK_TRIGGER_URL = "http://localhost:9090"


def _print_header(text: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")


def setup_subscriptions(manifest: dict, base_url: str) -> list[str]:
    """Create Statis subscriptions that fire webhooks to the crew trigger."""
    sub_ids = []
    with httpx.Client(timeout=10, verify=False) as client:
        headers = {"X-API-Key": manifest["master_key"]}

        # Subscription → Account Crew
        r = client.post(
            f"{base_url}/subscriptions",
            json={
                "entity_type": ENTITY_TYPE,
                "destination": f"{WEBHOOK_TRIGGER_URL}/account-crew",
            },
            headers=headers,
        )
        if r.status_code in (200, 201):
            sid = r.json()["subscription_id"]
            sub_ids.append(sid)
            print(f"  ✅ Subscription → Account Crew: {sid[:16]}...")

        # Subscription → Revenue Crew
        r = client.post(
            f"{base_url}/subscriptions",
            json={
                "entity_type": ENTITY_TYPE,
                "destination": f"{WEBHOOK_TRIGGER_URL}/revenue-crew",
            },
            headers=headers,
        )
        if r.status_code in (200, 201):
            sid = r.json()["subscription_id"]
            sub_ids.append(sid)
            print(f"  ✅ Subscription → Revenue Crew: {sid[:16]}...")

    return sub_ids


def run_support_crew(manifest: dict, base_url: str) -> None:
    """Team A: Support crew detects and classifies the crisis."""
    _print_header("TEAM A: SUPPORT CREW")

    triage = Agent(
        role="Support Triage",
        goal=f"Classify the incident and publish events for {ENTITY_TYPE}/{ENTITY_ID}.",
        backstory="You are Team A's triage specialist.",
        tools=[make_push_tool(get_key(manifest, "crewai_triage"), base_url)],
        verbose=True,
    )

    sentiment = Agent(
        role="Support Sentiment",
        goal=f"Analyze customer tone and publish events for {ENTITY_TYPE}/{ENTITY_ID}.",
        backstory="You are Team A's sentiment analyst.",
        tools=[make_push_tool(get_key(manifest, "crewai_sentiment"), base_url)],
        verbose=True,
    )

    triage_task = Task(
        description=(
            f"Classify this ticket: 'CRITICAL: Database cluster is down, "
            f"all writes failing, data loss possible.'\n\n"
            f"Publish support.incident_reported via statis_push_event:\n"
            f"  entity_type: {ENTITY_TYPE}, entity_id: {ENTITY_ID}\n"
            f"  payload: incident_id, type=outage, severity=critical, summary\n"
            f"  producer: crewai_triage"
        ),
        expected_output="Confirmation of published incident event.",
        agent=triage,
    )

    sentiment_task = Task(
        description=(
            f"Analyze: 'We are done. Cancel our contract immediately. This "
            f"is the worst service we have ever experienced.'\n\n"
            f"Publish support.sentiment_updated via statis_push_event:\n"
            f"  entity_type: {ENTITY_TYPE}, entity_id: {ENTITY_ID}\n"
            f"  payload: label=angry\n"
            f"  producer: crewai_sentiment"
        ),
        expected_output="Confirmation of published sentiment event.",
        agent=sentiment,
    )

    crew = Crew(
        agents=[triage, sentiment],
        tasks=[triage_task, sentiment_task],
        process=Process.sequential,
        verbose=True,
    )
    crew.kickoff()


def main() -> None:
    if "--reprovision" in sys.argv and CACHE_FILE.exists():
        CACHE_FILE.unlink()

    _print_header("DEMO 3: MULTI-CREW PIPELINE")
    print("Three independent teams connected through Statis webhooks.\n")
    print("Prerequisites:")
    print("  1. Statis API running")
    print("  2. python webhook_crew_trigger.py (in another terminal)")
    print("  3. cd worker && python main.py (in another terminal)\n")

    manifest = provision()
    base_url = manifest.get("base_url", "http://localhost:8000")

    print(f"Entity: {ENTITY_TYPE}/{ENTITY_ID}\n")

    # Setup webhook subscriptions
    _print_header("SETTING UP WEBHOOK SUBSCRIPTIONS")
    sub_ids = setup_subscriptions(manifest, base_url)

    # Run Support Crew (Team A)
    # This publishes events → Statis materializes state → worker delivers
    # webhooks → webhook_crew_trigger.py spawns Account + Revenue crews
    run_support_crew(manifest, base_url)

    _print_header("WAITING FOR WEBHOOK DELIVERY + CREW TRIGGERS")
    print("  The Statis worker is now delivering webhooks to the crew trigger.")
    print("  Account and Revenue crews should be spawning automatically...\n")

    # Give the worker + downstream crews time to process
    for i in range(6):
        time.sleep(5)
        print(f"  ⏳ Waiting... ({(i+1)*5}s)")

    # Show final state
    _print_header("FINAL STATE (ALL TEAMS COMBINED)")
    with httpx.Client(timeout=10, verify=False) as client:
        r = client.get(
            f"{base_url}/state/{ENTITY_TYPE}/{ENTITY_ID}",
            headers={"X-API-Key": manifest["master_key"]},
        )
        if r.status_code == 200:
            data = r.json()
            print(f"  state_version: {data['state_version']}")
            print(f"  state_hash:    {data.get('state_hash', 'n/a')[:24]}...")
            for k, v in data.get("state", {}).items():
                print(f"  {k:16s}: {v}")

    print()
    print("  Three independent crews, zero shared code, connected")
    print("  by Statis subscriptions and webhooks. Enterprise-grade.")
    print()


if __name__ == "__main__":
    main()
