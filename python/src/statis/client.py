from __future__ import annotations

import os
import time
import uuid
from typing import Any, Optional

import httpx

from ._models import (
    ActionDeniedError,
    ActionEscalatedError,
    ActionTimeoutError,
    Receipt,
    SimulateResult,
    StatisActionDenied,
    StatisActionEscalated,
    StatisError,
)


class StatisClient:
    """Synchronous client for the Statis API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.statis.dev",
        timeout: float = 30.0,
        poll_interval: float = 0.5,
    ) -> None:
        resolved_key = api_key or os.environ.get("STATIS_API_KEY", "")
        self._poll_interval = poll_interval
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"X-API-Key": resolved_key},
            timeout=timeout,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def propose(
        self,
        action_type: str,
        target: dict[str, str],
        parameters: dict[str, Any],
        agent_id: str,
        target_system: str,
        action_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> str:
        """Propose an action and return the action_id."""
        body: dict[str, Any] = {
            "action_id": action_id or f"statis-{uuid.uuid4()}",
            "action_type": action_type,
            "target_entity": target,
            "parameters": parameters,
            "proposed_by": agent_id,
            "target_system": target_system,
            "context": context or {},
        }
        resp = self._http.post("/actions", json=body)
        self._raise_for_status(resp)
        return resp.json()["action_id"]

    def execute(
        self,
        action_type: str,
        target: dict[str, str],
        parameters: dict[str, Any],
        agent_id: str,
        target_system: str,
        action_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
        timeout: Optional[float] = None,
        poll_interval: Optional[float] = None,
    ) -> Receipt:
        """Propose, evaluate, wait for execution, and return the Receipt.

        Raises:
            ActionDeniedError: if the policy engine denies the action.
            ActionTimeoutError: if execution doesn't complete within *timeout* seconds.
        """
        aid = self.propose(
            action_type=action_type,
            target=target,
            parameters=parameters,
            agent_id=agent_id,
            target_system=target_system,
            action_id=action_id,
            context=context,
        )

        # Trigger evaluation
        resp = self._http.post(f"/actions/{aid}/evaluate")
        self._raise_for_status(resp)
        eval_data = resp.json()

        # Fast-path: evaluate response carries receipt_id and decision.
        # Terminal decisions are resolved immediately — no polling needed.
        eval_decision: str = eval_data.get("decision", "")
        if eval_decision == "DENIED":
            receipt = self.get_receipt(aid)
            raise ActionDeniedError(reason="Action denied by policy", receipt=receipt)
        if eval_decision == "ESCALATED":
            raise ActionEscalatedError(action_id=aid)
        if eval_decision == "APPROVED":
            return self.get_receipt(aid)

        # Fallback: poll until terminal status (handles unexpected states)
        deadline = time.monotonic() + (timeout or float("inf"))
        interval = poll_interval if poll_interval is not None else self._poll_interval

        while True:
            resp = self._http.get(f"/actions/{aid}")
            self._raise_for_status(resp)
            data = resp.json()
            status: str = data["status"]

            if status == "DENIED":
                receipt = self.get_receipt(aid)
                raise ActionDeniedError(reason="Action denied by policy", receipt=receipt)

            if status == "ESCALATED":
                raise ActionEscalatedError(action_id=aid)

            if status in ("COMPLETED", "FAILED"):
                return self.get_receipt(aid)

            if time.monotonic() >= deadline:
                raise ActionTimeoutError(action_id=aid, timeout=timeout or 0)

            time.sleep(interval)

    def simulate(
        self,
        action_type: str,
        entity_state: dict[str, Any],
        parameters: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> SimulateResult:
        """Dry-run policy evaluation. No DB writes, no receipt."""
        body: dict[str, Any] = {
            "action_type": action_type,
            "entity_state": entity_state,
            "parameters": parameters or {},
            "context": context or {},
        }
        resp = self._http.post("/actions/simulate", json=body)
        self._raise_for_status(resp)
        data = resp.json()
        return SimulateResult(
            decision=data["decision"],
            rule_id=data.get("rule_id"),
            rule_version=data.get("rule_version"),
            reason=data["reason"],
        )

    def get_action_status(self, action_id: str) -> str:
        """Return the current status string for an action (e.g. 'ESCALATED', 'COMPLETED')."""
        resp = self._http.get(f"/actions/{action_id}")
        self._raise_for_status(resp)
        return resp.json()["status"]

    def get_receipt(self, action_id: str) -> Receipt:
        """Fetch the receipt for a completed (or denied) action."""
        resp = self._http.get(f"/receipts/{action_id}")
        self._raise_for_status(resp)
        return self._parse_receipt(resp.json())

    def wait_for_completion(
        self,
        action_id: str,
        poll_interval: float = 2.0,
        timeout: float = 60.0,
    ) -> Receipt:
        """Poll GET /actions/{action_id} until the action reaches a terminal state.

        Returns the Receipt on COMPLETED.
        Raises StatisActionDenied on DENIED.
        Raises StatisActionEscalated on ESCALATED.
        Raises ActionTimeoutError if timeout is reached before a terminal state.
        """
        deadline = time.monotonic() + timeout

        while True:
            resp = self._http.get(f"/actions/{action_id}")
            self._raise_for_status(resp)
            data = resp.json()
            action_status: str = data["status"]

            if action_status == "COMPLETED":
                return self.get_receipt(action_id)

            if action_status == "DENIED":
                receipt = self.get_receipt(action_id)
                raise StatisActionDenied(
                    action_id=action_id,
                    rule_id=receipt.rule_id,
                    reason=f"Action denied by policy (rule={receipt.rule_id})",
                )

            if action_status == "ESCALATED":
                raise StatisActionEscalated(action_id=action_id)

            if time.monotonic() >= deadline:
                raise ActionTimeoutError(action_id=action_id, timeout=timeout)

            time.sleep(poll_interval)

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> StatisClient:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if not resp.is_success:
            try:
                msg = resp.json().get("detail", resp.text)
            except Exception:
                msg = resp.text
            raise StatisError(status_code=resp.status_code, message=msg)

    @staticmethod
    def _parse_receipt(data: dict[str, Any]) -> Receipt:
        from datetime import datetime

        def _dt(v: Optional[str]) -> Optional[datetime]:
            return datetime.fromisoformat(v) if v else None

        return Receipt(
            receipt_id=data["receipt_id"],
            action_id=data["action_id"],
            decision=data["decision"],
            rule_id=data.get("rule_id"),
            rule_version=data.get("rule_version"),
            approved_by=data["approved_by"],
            conditions_evaluated=data.get("conditions_evaluated"),
            execution_result=data.get("execution_result"),
            executed_at=_dt(data.get("executed_at")),
            hash=data["hash"],
            created_at=datetime.fromisoformat(data["created_at"]),
        )
