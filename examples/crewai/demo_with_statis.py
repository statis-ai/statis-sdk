#!/usr/bin/env python3
"""Demo 2 — Coordinated Response Crew WITH Statis.

Five CrewAI agents handle a customer crisis, coordinating through the Statis
event bus. After the crew finishes, the script showcases:
  • RBAC contrast: Billing (redacted) vs Admin (full) state view
  • Deterministic state hash + provenance
  • Time travel audit

This is Phase 2+3 of the showcase video.

Usage:
    python demo_with_statis.py
    python demo_with_statis.py --reprovision   # fresh tenant
"""
from __future__ import annotations

import json
import os
import sys

import httpx

from provision import provision, get_key, CACHE_FILE
from agents import create_agents
from tasks import create_tasks_with_statis, SCENARIO_CONTEXT
from crew import build_crew


def _print_header(text: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")


def _print_state(label: str, state: dict) -> None:
    print(f"\n  ── {label} ──")
    s = state.get("state", {})
    print(f"  state_version: {state.get('state_version')}")
    print(f"  state_hash:    {state.get('state_hash', 'n/a')[:24]}...")
    for k, v in s.items():
        print(f"  {k:16s}: {v}")
    print()


def main() -> None:
    # Handle --reprovision flag
    if "--reprovision" in sys.argv and CACHE_FILE.exists():
        CACHE_FILE.unlink()
        print("🗑  Cache cleared for fresh provisioning.\n")

    _print_header("STATIS + CREWAI: COORDINATED RESPONSE CREW")

    # ── Step 1: Provision ────────────────────────────────────────────
    print("🔑 Loading API keys...")
    manifest = provision()
    base_url = manifest.get("base_url", "http://localhost:8000")
    et = SCENARIO_CONTEXT["entity_type"]
    eid = SCENARIO_CONTEXT["entity_id"]
    print(f"   Tenant:  {manifest['tenant_id']}")
    print(f"   Entity:  {et}/{eid}")

    # ── Step 2: Run the Crew ─────────────────────────────────────────
    _print_header("PHASE 2: RUNNING THE CREW WITH STATIS")

    print("Scenario: A customer crisis hits — production outage, angry email,")
    print("five specialized agents handle it simultaneously through Statis.\n")

    agents = create_agents(manifest, et, eid)
    tasks = create_tasks_with_statis(agents)
    crew = build_crew(agents, tasks)

    result = crew.kickoff()

    _print_header("CREW RESULT")
    print(result)

    # ── Step 3: RBAC Contrast ────────────────────────────────────────
    _print_header("PHASE 3: RBAC CONTRAST — BILLING vs ADMIN")

    print("The Billing Agent's API key has role=billing.")
    print("The Master (Admin) key has no role restrictions.\n")

    with httpx.Client(timeout=10, verify=False) as client:
        # Billing view (redacted)
        r = client.get(
            f"{base_url}/state/{et}/{eid}",
            headers={"X-API-Key": get_key(manifest, "crewai_billing")},
        )
        if r.status_code == 200:
            _print_state("BILLING VIEW (role=billing, sentiment REDACTED)", r.json())
        else:
            print(f"  ⚠ Could not fetch state: HTTP {r.status_code}")

        # Admin view (full)
        r = client.get(
            f"{base_url}/state/{et}/{eid}",
            headers={"X-API-Key": manifest["master_key"]},
        )
        if r.status_code == 200:
            _print_state("ADMIN VIEW (master key, FULL state)", r.json())
        else:
            print(f"  ⚠ Could not fetch state: HTTP {r.status_code}")

    # ── Step 4: Determinism + Provenance ─────────────────────────────
    _print_header("DETERMINISTIC STATE HASH + PROVENANCE")

    with httpx.Client(timeout=10, verify=False) as client:
        r = client.get(
            f"{base_url}/state/{et}/{eid}",
            headers={"X-API-Key": manifest["master_key"]},
        )
        if r.status_code == 200:
            data = r.json()
            print(f"  state_hash:    {data.get('state_hash')}")
            print(f"  state_version: {data.get('state_version')}")
            provenance = data.get("provenance", [])
            print(f"  provenance:    {len(provenance)} events")
            for p in provenance:
                print(f"    → {p}")
        print()

    # ── Step 5: Time Travel ──────────────────────────────────────────
    _print_header("TIME TRAVEL: WHAT DID SALES KNOW?")

    with httpx.Client(timeout=10, verify=False) as client:
        r = client.get(
            f"{base_url}/state/{et}/{eid}",
            headers={"X-API-Key": manifest["master_key"]},
        )
        if r.status_code == 200:
            final_version = r.json().get("state_version", 1)
            # Show state at revision 1 vs final
            for rev in [1, final_version]:
                r2 = client.get(
                    f"{base_url}/state/{et}/{eid}/at",
                    params={"rev": rev},
                    headers={"X-API-Key": manifest["master_key"]},
                )
                if r2.status_code == 200:
                    _print_state(f"STATE AT REVISION {rev}", r2.json())

    _print_header("DEMO COMPLETE")
    print(f"  Console:  Open the Statis Console to see the full timeline.")
    print(f"  Entity:   {et}/{eid}")
    print(f"  Tenant:   {manifest['tenant_id']}")
    print()


if __name__ == "__main__":
    main()
