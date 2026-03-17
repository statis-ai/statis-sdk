"""Provision-once-cache: signup + per-agent API keys for the CrewAI demo.

First run:  calls /admin/signup + /admin/api-keys, writes .statis_demo_keys.json
Next runs:  loads from cache, validates master key with GET /health
Force new:  pass --reprovision to ignore cache and create a fresh tenant
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

CACHE_FILE = Path(__file__).parent / ".statis_demo_keys.json"

# Per-agent key definitions (label, role, agent_id)
AGENT_KEYS = [
    ("Triage Agent",    "support",  "crewai_triage"),
    ("Sentiment Agent", "support",  "crewai_sentiment"),
    ("CSM Agent",       "csm",      "crewai_csm"),
    ("Sales Agent",     "sales",    "crewai_sales"),
    ("Billing Agent",   "billing",  "crewai_billing"),
]


def _base_url() -> str:
    return os.getenv("STATIS_API_URL", "http://localhost:8000")


def provision(base_url: str | None = None) -> dict:
    """Return the full key manifest, provisioning if needed."""
    url = base_url or _base_url()

    if CACHE_FILE.exists():
        data = json.loads(CACHE_FILE.read_text())
        # Quick health-check to make sure the API is reachable
        try:
            r = httpx.get(f"{url}/health", timeout=5, verify=False)
            r.raise_for_status()
        except Exception:
            print("⚠  API unreachable but cached keys found — using cache anyway.")
        return data

    return _provision_fresh(url)


def _provision_fresh(base_url: str) -> dict:
    """Create a new tenant, 5 agent keys, and write the cache file."""
    print("🔑 Provisioning new tenant and agent keys...")

    # Wake up the server first (Render free tier sleeps after inactivity)
    print("   Waking up API server (may take up to 60s on free tier)...")
    try:
        httpx.get(f"{base_url}/health", timeout=90, verify=False)
        print("   ✅ API is awake.")
    except Exception:
        print("   ⚠  Health check timed out, trying signup anyway...")

    with httpx.Client(base_url=base_url, timeout=120, verify=False) as client:
        # 1. Signup — creates tenant + master key
        r = client.post("/admin/signup", json={
            "email": "demo@statis.dev",
            "project_name": "CrewAI Demo",
        })
        r.raise_for_status()
        signup = r.json()

        master_key = signup["api_key"]
        tenant_id = signup["tenant_id"]
        print(f"   Tenant:     {tenant_id}")
        print(f"   Master key: {master_key[:12]}...")

        # 2. Create per-agent keys
        agent_keys: dict[str, dict] = {}
        for label, role, agent_id in AGENT_KEYS:
            r = client.post(
                "/admin/api-keys",
                json={"label": label, "role": role, "agent_id": agent_id},
                headers={"X-API-Key": master_key},
            )
            r.raise_for_status()
            key_data = r.json()
            agent_keys[agent_id] = {
                "raw_key": key_data["raw_key"],
                "label": label,
                "role": role,
                "agent_id": agent_id,
            }
            print(f"   {label:20s} -> {key_data['raw_key'][:12]}... (role={role})")

    manifest = {
        "tenant_id": tenant_id,
        "master_key": master_key,
        "agent_keys": agent_keys,
        "base_url": base_url,
    }
    CACHE_FILE.write_text(json.dumps(manifest, indent=2))
    print(f"\n✅ Keys cached to {CACHE_FILE.name}")
    return manifest


def get_key(manifest: dict, agent_id: str) -> str:
    """Convenience: return the raw API key for a given agent_id."""
    return manifest["agent_keys"][agent_id]["raw_key"]


# ── CLI entry point ──────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Provision Statis keys for CrewAI demo")
    parser.add_argument("--reprovision", action="store_true", help="Ignore cache, create fresh tenant")
    parser.add_argument("--base-url", default=None, help="Statis API URL")
    args = parser.parse_args()

    url = args.base_url or _base_url()

    if args.reprovision and CACHE_FILE.exists():
        CACHE_FILE.unlink()
        print("🗑  Cache cleared.")

    manifest = provision(url)

    print(f"\nTenant:     {manifest['tenant_id']}")
    print(f"Master key: {manifest['master_key'][:12]}...")
    print(f"Agent keys: {len(manifest['agent_keys'])}")
    for aid, info in manifest["agent_keys"].items():
        print(f"  {info['label']:20s}  role={info['role']:10s}  key={info['raw_key'][:12]}...")


if __name__ == "__main__":
    main()
