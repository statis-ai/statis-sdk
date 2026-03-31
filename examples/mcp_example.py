"""
MCP + Statis governance example.

Demonstrates how to wrap an MCP tool call through Statis in shadow mode.
Shadow mode evaluates the action and writes a receipt — but never calls any
external system — so this example runs safely without production credentials.

What this example covers:
  1. Initialise a StatisClient pointed at localhost (or any Statis API).
  2. Create a StatisMCPMiddleware in shadow mode.
  3. Call execute_tool() to route a tool call through governance.
  4. Inspect the result dict (receipt_id, decision, status, result).
  5. Handle ActionDeniedError if policy rejects the call.

To run against a real Statis API:
  export STATIS_API_KEY=your_key
  python examples/mcp_example.py

To run in dry-run (no server required):
  python examples/mcp_example.py --dry-run
"""
from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# Optional dry-run stub — lets the example run with no running server.
# Omit this block if you have a live Statis instance.
# ---------------------------------------------------------------------------

DRY_RUN = "--dry-run" in sys.argv or os.getenv("STATIS_DRY_RUN") == "1"


class _StubReceipt:
    """Minimal receipt stub used when DRY_RUN=True."""

    def __init__(self, tool_name: str) -> None:
        self.receipt_id = "dry-run-receipt-0001"
        self.decision = "APPROVED"
        self.execution_result = {
            "note": "dry-run — no server contacted",
            "tool": tool_name,
        }


class _StubClient:
    """Drop-in StatisClient replacement for dry-run mode."""

    def execute(
        self,
        action_type: str,
        target: dict,
        parameters: dict,
        agent_id: str,
        target_system: str,
        **kwargs,
    ) -> _StubReceipt:
        print(
            f"[dry-run] would propose action_type={action_type!r} "
            f"parameters={parameters} as {agent_id!r} -> {target_system!r}"
        )
        return _StubReceipt(action_type)


# ---------------------------------------------------------------------------
# Real example
# ---------------------------------------------------------------------------

from statis import StatisClient, StatisMCPMiddleware
from statis._models import ActionDeniedError, ActionEscalatedError


def main() -> None:
    # Step 1: Create a Statis client.
    # In shadow mode the API still needs to receive the proposal and write a
    # receipt, so a real (or local) Statis instance is required unless you
    # pass --dry-run.
    if DRY_RUN:
        print("Running in dry-run mode. No server required.\n")
        client = _StubClient()  # type: ignore[assignment]
    else:
        api_key = os.getenv("STATIS_API_KEY", "demo-key")
        base_url = os.getenv("STATIS_BASE_URL", "http://localhost:8000")
        client = StatisClient(api_key=api_key, base_url=base_url)

    # Step 2: Wrap the client in MCP middleware.
    # mode="shadow" means Statis evaluates and receipts the call but never
    # routes it to any downstream system — zero production risk.
    middleware = StatisMCPMiddleware(
        statis_client=client,
        mode="shadow",
        target_system="mcp",
    )

    # Step 3: Define the tool call you want to govern.
    # In a real MCP setup this would come from your MCP server's tool list.
    tool_name = "send_email"
    tool_input = {
        "to": "alice@example.com",
        "subject": "Quarterly Report",
        "body": "Please find the Q1 report attached.",
    }

    print(f"Proposing tool call: {tool_name!r}")
    print(f"Input: {tool_input}\n")

    # Step 4: Route the tool call through Statis governance.
    try:
        result = middleware.execute_tool(
            tool_name=tool_name,
            tool_input=tool_input,
            proposed_by="my-mcp-agent",  # agent identifier for audit trail
        )

        # Step 5: Inspect the result.
        print("Governance result:")
        print(f"  receipt_id : {result['receipt_id']}")
        print(f"  decision   : {result['decision']}")
        print(f"  status     : {result['status']}")
        print(f"  result     : {result['result']}")
        print()
        print(
            "In shadow mode the tool was NOT called. "
            "The receipt is written to the Statis ledger for audit purposes."
        )

    except ActionDeniedError as exc:
        # The policy engine evaluated the proposal and denied it.
        # Surface this to the agent so it does not retry blindly.
        print(f"Action DENIED by policy: {exc.reason}")
        print(f"Receipt ID: {exc.receipt.receipt_id}")
        sys.exit(1)

    except ActionEscalatedError as exc:
        # A human reviewer must approve before execution proceeds.
        # The agent should stop and wait — do not retry automatically.
        print(f"Action ESCALATED for human review. Action ID: {exc.action_id}")
        print("Open the Statis Console to approve or reject.")
        sys.exit(1)


if __name__ == "__main__":
    main()
