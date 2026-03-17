#!/usr/bin/env python3
"""Webhook crew trigger — receives Statis state-change webhooks and spawns
CrewAI crew runs.

Used by Demo 3 (Multi-Crew Pipeline). Each team's crew is independent;
Statis subscriptions fire webhooks to this receiver, which decides which
crew to spawn.

Usage:
    python webhook_crew_trigger.py
    # Runs on port 9090 by default
"""
from __future__ import annotations

import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from provision import provision, get_key

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

PORT = 9090


class WebhookHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler that receives Statis webhooks and routes them."""

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return

        logger.info(
            "Webhook received: entity=%s/%s version=%s",
            payload.get("entity_type"),
            payload.get("entity_id"),
            payload.get("state_version"),
        )

        # Route to the appropriate crew based on the webhook path
        path = self.path.strip("/")

        if path == "account-crew":
            logger.info("  → Triggering Account Management Crew")
            threading.Thread(
                target=_run_account_crew, args=(payload,), daemon=True
            ).start()
        elif path == "revenue-crew":
            logger.info("  → Triggering Revenue Operations Crew")
            threading.Thread(
                target=_run_revenue_crew, args=(payload,), daemon=True
            ).start()
        else:
            logger.info(f"  → Unknown webhook path: /{path}")

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, format, *args):
        pass  # Suppress default logging


def _run_account_crew(payload: dict) -> None:
    """Spawn the Account Management crew (Team B)."""
    from crewai import Agent, Crew, Process, Task
    from statis_tools import make_read_tool, make_push_tool

    manifest = provision()
    base_url = manifest.get("base_url", "http://localhost:8000")
    et = payload.get("entity_type", "account")
    eid = payload.get("entity_id", "unknown")

    csm = Agent(
        role="Account CSM",
        goal=f"Read state for {et}/{eid} and decide on customer success actions.",
        backstory="You are triggered by a state-change webhook from Statis.",
        tools=[
            make_read_tool(get_key(manifest, "crewai_csm"), base_url),
            make_push_tool(get_key(manifest, "crewai_csm"), base_url),
        ],
        verbose=True,
    )

    task = Task(
        description=(
            f"A state change was detected for {et}/{eid}.\n"
            f"Read the current state using statis_read_state and decide "
            f"whether to escalate. If churn_risk is true, publish a "
            f"csm.escalation_requested event."
        ),
        expected_output="Your assessment and any escalation actions taken.",
        agent=csm,
    )

    crew = Crew(agents=[csm], tasks=[task], process=Process.sequential, verbose=True)
    result = crew.kickoff()
    logger.info("Account Crew completed: %s", str(result)[:200])


def _run_revenue_crew(payload: dict) -> None:
    """Spawn the Revenue Operations crew (Team C)."""
    from crewai import Agent, Crew, Process, Task
    from statis_tools import make_read_tool

    manifest = provision()
    base_url = manifest.get("base_url", "http://localhost:8000")
    et = payload.get("entity_type", "account")
    eid = payload.get("entity_id", "unknown")

    sales = Agent(
        role="Revenue Sales Agent",
        goal=f"Read state for {et}/{eid} and adjust outreach.",
        backstory="You are triggered by a state-change webhook from Statis.",
        tools=[make_read_tool(get_key(manifest, "crewai_sales"), base_url)],
        verbose=True,
    )

    billing = Agent(
        role="Revenue Billing Agent",
        goal=f"Read state for {et}/{eid} and adjust dunning.",
        backstory="You are triggered by a state-change webhook from Statis.",
        tools=[make_read_tool(get_key(manifest, "crewai_billing"), base_url)],
        verbose=True,
    )

    sales_task = Task(
        description=f"Read state for {et}/{eid} and decide on sales outreach.",
        expected_output="Your outreach decision.",
        agent=sales,
    )

    billing_task = Task(
        description=f"Read state for {et}/{eid} and decide on dunning.",
        expected_output="Your dunning decision.",
        agent=billing,
    )

    crew = Crew(
        agents=[sales, billing],
        tasks=[sales_task, billing_task],
        process=Process.sequential,
        verbose=True,
    )
    result = crew.kickoff()
    logger.info("Revenue Crew completed: %s", str(result)[:200])


def main() -> None:
    print(f"🔗 Webhook Crew Trigger listening on http://localhost:{PORT}")
    print(f"   POST /account-crew  → spawns Account Management Crew")
    print(f"   POST /revenue-crew  → spawns Revenue Operations Crew")
    print()

    server = HTTPServer(("", PORT), WebhookHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Shutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
