"""Mock Stripe adapter — simulates apply_discount without a real API call."""
from __future__ import annotations

import time
from typing import Any

from app.adapters.base import BaseAdapter, ExecutionResult


class MockStripeAdapter(BaseAdapter):
    """Handles action_type == 'apply_discount' (and retention_offer for demo).

    Simulates a 50 ms network round-trip so the worker logs look realistic.
    Uses action_id as the idempotency key — safe to call more than once.
    """

    _SUPPORTED = {"apply_discount", "retention_offer"}

    def execute(self, action: Any) -> ExecutionResult:
        time.sleep(0.05)  # simulate network latency

        action_id: str = (
            action.action_id if hasattr(action, "action_id") else action["action_id"]
        )
        action_type: str = (
            action.action_type
            if hasattr(action, "action_type")
            else action["action_type"]
        )

        if action_type not in self._SUPPORTED:
            return ExecutionResult(
                success=False,
                result={},
                error=f"MockStripeAdapter does not handle action_type={action_type!r}",
            )

        return ExecutionResult(
            success=True,
            result={"charge_id": f"ch_mock_{action_id[:8]}"},
            error=None,
        )
