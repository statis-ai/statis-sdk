#!/usr/bin/env python3
"""CSM coordination demo — Account State Pack.

Posts a realistic sequence of events to the Statis API and prints the
materialized account state after each step, showing how a CSM (or any
consumer) can always retrieve the golden record.

With --webhook-url: creates a subscription so the worker will push state
to the given URL; after posting events, prints delivery trace summary.

Usage:
    # Start the API first:
    #   cd api && uvicorn app.main:app --reload
    python examples/csm_demo.py [--base-url http://localhost:8000]
    python examples/csm_demo.py --webhook-url http://localhost:9999/
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    import httpx
except ImportError:
    print("This demo requires the 'httpx' package:  pip install httpx")
    sys.exit(1)


ENTITY_TYPE = "account"
ENTITY_ID = f"acc_demo_{uuid.uuid4().hex[:8]}"

SCENARIO: List[Tuple[str, str, Dict[str, Any], str]] = [
    (
        "Step 1: Support ticket opened",
        "support.ticket_updated",
        {"ticket_id": "t_100", "status": "open", "occurred_at": "2026-02-19T09:00:00Z"},
        "system",
    ),
    (
        "Step 2: Major incident reported (DB outage, high severity)",
        "support.incident_reported",
        {
            "incident_id": "inc_200",
            "type": "outage",
            "status": "open",
            "severity": "high",
            "summary": "Production DB outage",
            "occurred_at": "2026-02-19T09:05:00Z",
        },
        "system",
    ),
    (
        "Step 3: Billing upgrades the account to Enterprise",
        "billing.plan_changed",
        {"plan": "enterprise"},
        "system",
    ),
    (
        "Step 4: Sentiment detected as negative",
        "support.sentiment_updated",
        {"label": "negative", "updated_at": "2026-02-19T09:10:00Z"},
        "human",
    ),
    (
        "Step 5: CSM requests escalation to sales",
        "csm.escalation_requested",
        {"owner": "sales", "action": "schedule QBR call", "reason": "churn risk after outage"},
        "agent",
    ),
    (
        "Step 6: Support ticket resolved",
        "support.ticket_updated",
        {"ticket_id": "t_100", "status": "closed", "occurred_at": "2026-02-19T09:25:00Z"},
        "system",
    ),
    (
        "Step 7: Billing downgrades to Pro (customer requested)",
        "billing.plan_changed",
        {"plan": "pro"},
        "system",
    ),
]


def post_event(client: httpx.Client, base_url: str, event_id: str,
               event_type: str, payload: dict, producer: str) -> int:
    body = {
        "event_id": event_id,
        "entity_type": ENTITY_TYPE,
        "entity_id": ENTITY_ID,
        "event_type": event_type,
        "payload": payload,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "producer": producer,
        "schema_version": "1",
    }
    r = client.post(f"{base_url}/events", json=body)
    r.raise_for_status()
    return r.status_code


def get_state(client: httpx.Client, base_url: str) -> dict:
    r = client.get(f"{base_url}/state/{ENTITY_TYPE}/{ENTITY_ID}")
    if r.status_code == 404:
        return {}
    r.raise_for_status()
    return r.json()


def create_subscription(client: httpx.Client, base_url: str, destination: str) -> str:
    body = {"entity_type": ENTITY_TYPE, "destination": destination}
    r = client.post(f"{base_url}/subscriptions", json=body)
    r.raise_for_status()
    data = r.json()
    return data["subscription_id"]


def get_delivery_trace(client: httpx.Client, base_url: str, subscription_id: str) -> list:
    r = client.get(f"{base_url}/delivery-trace/{subscription_id}", params={"limit": 50})
    r.raise_for_status()
    return r.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="CSM demo for Statis")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument(
        "--webhook-url",
        default=None,
        metavar="URL",
        help="Create a subscription with this destination; after events, show delivery trace",
    )
    args = parser.parse_args()

    print(f"=== Statis CSM Demo ===")
    print(f"Entity: {ENTITY_TYPE}/{ENTITY_ID}")
    print(f"API:    {args.base_url}\n")

    subscription_id: Optional[str] = None
    with httpx.Client(timeout=10) as client:
        if args.webhook_url:
            subscription_id = create_subscription(client, args.base_url, args.webhook_url)
            print(f"Subscription created: {subscription_id}")
            print(f"  destination: {args.webhook_url}")
            print()

        for i, (desc, event_type, payload, producer) in enumerate(SCENARIO, start=1):
            event_id = f"demo_{ENTITY_ID}_{i}"
            print(f"--- {desc} ---")
            print(f"  event_type: {event_type}")
            print(f"  payload:    {json.dumps(payload, indent=2)}")

            status = post_event(client, args.base_url, event_id,
                                event_type, payload, producer)
            print(f"  POST /events -> {status}")

            state = get_state(client, args.base_url)
            if state:
                s = state["state"]
                print(f"  state_version: {state['state_version']}")
                print(f"  state_hash:    {state['state_hash'][:16]}...")
                print(f"  plan:          {s.get('plan')}")
                print(f"  churn_risk:    {s.get('churn_risk')}")
                print(f"  blockers:      {s.get('blockers')}")
                print(f"  risk_flags:    {s.get('risk_flags')}")
                print(f"  sentiment:     {s.get('sentiment')}")
                print(f"  open_incidents:{len(s.get('open_incidents', []))}")
                print(f"  next_actions:  {len(s.get('next_actions', []))}")
            print()

        if subscription_id:
            print("=== Pushes to receivers ===")
            print("Start the worker to deliver to your webhook (e.g. python worker/main.py).")
            print("Polling delivery trace a few times...\n")
            for attempt in range(3):
                time.sleep(2)
                trace = get_delivery_trace(client, args.base_url, subscription_id)
                pending = sum(1 for d in trace if d.get("status") == "pending")
                sent = sum(1 for d in trace if d.get("status") == "sent")
                failed = sum(1 for d in trace if d.get("status") == "failed")
                dead = sum(1 for d in trace if d.get("status") == "dead")
                print(f"  Trace ({len(trace)} deliveries): pending={pending}, sent={sent}, failed={failed}, dead={dead}")
            print(f"\nDelivery trace: curl {args.base_url}/delivery-trace/{subscription_id}")
            print()

    print("=== Demo complete ===")
    print(f"Retrieve final state:  curl {args.base_url}/state/{ENTITY_TYPE}/{ENTITY_ID}")


if __name__ == "__main__":
    main()
