#!/usr/bin/env python3
"""Statis Retention Demo — end-to-end churn retention flow.

Demonstrates all four primitives in a single script:
  P1  Action Contract   — agent proposes an action
  P2  Policy Engine     — rule evaluates and approves it
  P3  Execution Worker  — action executed exactly once via MockStripeAdapter
  P4  Receipt           — tamper-evident audit record returned to caller

Usage:
    STATIS_API_KEY=<key> python examples/retention_demo.py
    STATIS_API_KEY=<key> STATIS_BASE_URL=https://your-api.com python examples/retention_demo.py

Prerequisites:
    pip install httpx
    A running Statis API server and a valid API key.
    DATABASE_URL must be set if the execution worker cannot reach the default local DB.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime, timezone

try:
    import httpx
except ImportError:
    print("This demo requires httpx:  pip install httpx")
    sys.exit(1)

# ── path setup ────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "api"))  # app.*
sys.path.insert(0, _ROOT)                        # worker.*

# ── config ────────────────────────────────────────────────────────────────
BASE_URL = os.getenv("STATIS_BASE_URL", "http://localhost:8000")
API_KEY = os.getenv("STATIS_API_KEY", "")

ENTITY_TYPE = "account"
ENTITY_ID = "acct-42"
# Fresh action ID each run so the demo always succeeds on repeat.
# action_id[:8] = "act-demo" → charge_id = ch_mock_act-demo
ACTION_ID = f"act-demo-{datetime.now(timezone.utc).strftime('%H%M%S')}"

HEADERS = {"X-API-Key": API_KEY}


# ── helpers ───────────────────────────────────────────────────────────────

def _sep(label: str = "") -> None:
    line = f"\n── {label} " + "─" * max(0, 52 - len(label))
    print(line)


def _post_event(
    client: httpx.Client,
    event_id: str,
    event_type: str,
    payload: dict,
    producer: str = "system",
) -> None:
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
    r = client.post(f"{BASE_URL}/events", json=body, headers=HEADERS)
    r.raise_for_status()


def _get_state(client: httpx.Client) -> dict:
    r = client.get(f"{BASE_URL}/state/{ENTITY_TYPE}/{ENTITY_ID}", headers=HEADERS)
    if r.status_code == 404:
        return {}
    r.raise_for_status()
    return r.json()


def _get_action(client: httpx.Client, action_id: str) -> dict | None:
    r = client.get(f"{BASE_URL}/actions/{action_id}", headers=HEADERS)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def _worker_loop(stop: threading.Event) -> None:
    """Run the execution worker in a background thread."""
    import traceback
    try:
        from worker.execute import make_session_factory, run_once
        sf = make_session_factory()
        print("[worker] started", flush=True)
    except Exception as e:
        print(f"[worker] STARTUP ERROR: {e}", flush=True)
        traceback.print_exc()
        return
    while not stop.is_set():
        try:
            n = run_once(sf)
            if n:
                print(f"[worker] processed {n} action(s)", flush=True)
        except Exception as e:
            print(f"[worker] ERROR: {e}", flush=True)
            traceback.print_exc()
        time.sleep(0.25)


def _wait_for_completion(
    client: httpx.Client,
    action_id: str,
    timeout: float = 10.0,
) -> str | None:
    """Poll GET /actions/{id} every 500 ms until terminal status or timeout."""
    terminal = {"COMPLETED", "FAILED"}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        action = _get_action(client, action_id)
        if action and action["status"] in terminal:
            return action["status"]
        time.sleep(0.5)
    return None


# ── main demo ─────────────────────────────────────────────────────────────

def main() -> None:
    if not API_KEY:
        print("ERROR: set STATIS_API_KEY before running this demo")
        sys.exit(1)

    print("╔══════════════════════════════════════════════════════╗")
    print("║      Statis Retention Demo — All Four Primitives     ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"API:       {BASE_URL}")
    print(f"Entity:    {ENTITY_TYPE}/{ENTITY_ID}")
    print(f"Action ID: {ACTION_ID}")
    print()

    results: dict = {}
    receipt: dict = {}

    with httpx.Client(timeout=10) as client:

        # ── Step 1: Build entity state ────────────────────────────────
        _sep("Step 1 — Build entity state via events")

        ts = datetime.now(timezone.utc).strftime("%H%M%S%f")
        _post_event(client, f"ev-{ts}-created",    "account.created",           {})
        _post_event(client, f"ev-{ts}-ltv",        "billing.ltv_updated",       {"ltv": 1200})
        _post_event(client, f"ev-{ts}-churn",      "account.churn_risk_updated", {"churn_risk": True})

        state_data = _get_state(client)
        s = state_data.get("state", {})
        ltv = s.get("ltv", 0)
        churn = s.get("churn_risk", False)
        print(f"Customer {ENTITY_ID} ready:  ltv=${ltv},  churn_risk={'HIGH' if churn else 'LOW'}")
        print(f"State version: {state_data.get('state_version')}   "
              f"hash: {state_data.get('state_hash', '')[:16]}...")
        results["setup"] = True

        # ── Step 2: Agent proposes action (P1) ────────────────────────
        _sep("Step 2 — Agent proposes action  [Primitive 1: Action Contract]")

        action_body = {
            "action_id": ACTION_ID,
            "proposed_by": "retention-agent-v1",
            "action_type": "retention_offer",
            "target_entity": {"entity_type": ENTITY_TYPE, "entity_id": ENTITY_ID},
            "target_system": "stripe",
            "parameters": {"discount_pct": 10, "duration_days": 30},
            "context": {"reason": "churn_risk=HIGH, ltv=1200"},
        }
        r = client.post(f"{BASE_URL}/actions", json=action_body, headers=HEADERS)
        r.raise_for_status()
        print(f"Agent proposed action {ACTION_ID}")
        print(f"Status: {r.json()['status']}")
        results["propose"] = True

        # ── Step 3: Policy evaluation (P2) ───────────────────────────
        _sep("Step 3 — Policy evaluation       [Primitive 2: Policy Engine]")

        r = client.post(f"{BASE_URL}/actions/{ACTION_ID}/evaluate", headers=HEADERS)
        r.raise_for_status()
        eval_data = r.json()
        print(f"Policy decision:  {eval_data['decision']}")
        print(f"Rule:             {eval_data.get('rule_id')} v{eval_data.get('rule_version')}")
        print(f"Reason:           {eval_data['reason']}")
        print(f"Receipt ID:       {eval_data['receipt_id']}")
        results["evaluate"] = eval_data["decision"]

        if eval_data["decision"] != "APPROVED":
            print("\n⚠  Action was not APPROVED.")
            print("   Check that the entity state has ltv ≥ 1000, churn_risk=true, "
                  "and no recent discount.")
            sys.exit(1)

        # ── Step 4: Execution worker (P3) ────────────────────────────
        _sep("Step 4 — Execution worker         [Primitive 3: Execution Guarantee]")

        stop_flag = threading.Event()
        worker = threading.Thread(target=_worker_loop, args=(stop_flag,), daemon=True)
        worker.start()
        print("Execution worker started in background thread")
        print("Polling for COMPLETED status (up to 10 s)...")

        final_status = _wait_for_completion(client, ACTION_ID, timeout=10.0)
        stop_flag.set()

        if final_status is None:
            print("ERROR: Action did not reach COMPLETED within 10 s")
            sys.exit(1)

        print(f"Action status: {final_status}")
        results["execute"] = final_status

        # ── Step 5: Fetch receipt (P4) ────────────────────────────────
        _sep("Step 5 — Audit receipt            [Primitive 4: Receipt]")

        r = client.get(f"{BASE_URL}/receipts/{ACTION_ID}", headers=HEADERS)
        r.raise_for_status()
        receipt = r.json()
        exec_result = receipt.get("execution_result") or {}
        charge_id = exec_result.get("charge_id", "—")

        print(f"Receipt ID:       {receipt['receipt_id']}")
        print(f"Decision:         {receipt['decision']}")
        print(f"Rule:             {receipt.get('rule_id')} v{receipt.get('rule_version')}")
        print(f"Approved by:      {receipt['approved_by']}")
        print(f"Executed at:      {receipt.get('executed_at')}")
        print(f"Charge ID:        {charge_id}")
        print(f"Hash (SHA-256):   {receipt['hash']}")
        results["receipt_id"] = receipt["receipt_id"]
        results["charge_id"] = charge_id

        # ── Step 6: Idempotency proof ─────────────────────────────────
        _sep("Step 6 — Idempotency proof")

        r_dup = client.post(f"{BASE_URL}/actions", json=action_body, headers=HEADERS)
        if r_dup.status_code == 409:
            print(f"Duplicate propose blocked:  409  (action_id already exists)")
            results["idempotency_propose"] = True
        else:
            print(f"UNEXPECTED propose status: {r_dup.status_code}")

        r_re_eval = client.post(
            f"{BASE_URL}/actions/{ACTION_ID}/evaluate", headers=HEADERS
        )
        if r_re_eval.status_code == 409:
            print(f"Re-evaluation blocked:      409  (already in status '{final_status}')")
            results["idempotency_evaluate"] = True
        else:
            print(f"UNEXPECTED evaluate status: {r_re_eval.status_code}")

    # ── Summary ───────────────────────────────────────────────────────────
    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║                    Demo Complete                     ║")
    print("╚══════════════════════════════════════════════════════╝")
    rule_line = f"{receipt.get('rule_id')} v{receipt.get('rule_version')}"
    print(f"✓ Action proposed:          {ACTION_ID}")
    print(f"✓ Policy evaluated:         {results.get('evaluate')} ({rule_line})")
    print(f"✓ Executed once:            charge_id {results.get('charge_id')}")
    print(f"✓ Receipt generated:        {results.get('receipt_id')}")
    if results.get("idempotency_propose"):
        print(f"✓ Duplicate propose blocked: 409")
    if results.get("idempotency_evaluate"):
        print(f"✓ Re-evaluation blocked:     409")
    print()


if __name__ == "__main__":
    main()
