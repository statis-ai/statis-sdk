#!/usr/bin/env python3
"""Demo 2 — Coordinated Response Crew WITHOUT Statis.

The same five agents, same scenario, but NO shared state. This is the
"failure" run — Phase 1 of the showcase video.

The hook: Sales sends an upsell email to a customer whose system is down.

Usage:
    python demo_without_statis.py
"""
from __future__ import annotations

from agents import create_agents_without_statis
from tasks import create_tasks_without_statis, SCENARIO_CONTEXT
from crew import build_crew


def _print_header(text: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")


def main() -> None:
    _print_header("CREWAI WITHOUT STATIS: THE FAILURE SCENARIO")

    print("Scenario: Same crisis — production outage, angry customer.")
    print("But this time, agents have NO shared state. No event bus.")
    print("Each agent works in isolation.\n")
    print("Watch what happens when Sales has no visibility...\n")

    agents = create_agents_without_statis()
    tasks = create_tasks_without_statis(agents)
    crew = build_crew(agents, tasks)

    result = crew.kickoff()

    _print_header("CREW RESULT (WITHOUT STATIS)")
    print(result)

    _print_header("THE PROBLEM")
    print("  ❌ Sales just sent an upsell email to a customer whose")
    print("     system has been down for 30 minutes.")
    print()
    print("  ❌ Billing proceeded with dunning retries during an outage.")
    print()
    print("  ❌ The CSM had no real-time data — made assumptions instead")
    print("     of reading the golden record.")
    print()
    print("  ❌ No audit trail. No provenance. No determinism.")
    print()
    print("  → Run demo_with_statis.py to see the coordinated version.")
    print()


if __name__ == "__main__":
    main()
