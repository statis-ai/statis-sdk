"""MCP (Model Context Protocol) middleware for Statis governance.

StatisMCPMiddleware intercepts MCP tool calls and routes them through the
Statis governance lifecycle (propose -> evaluate -> receipt) before the tool
executes. Compatible with any Python MCP client that exposes tool name +
input dict — no MCP SDK dependency required.

Usage::

    from statis import StatisClient, StatisMCPMiddleware

    client = StatisClient(api_key="...", base_url="https://api.statis.dev")

    middleware = StatisMCPMiddleware(
        statis_client=client,
        mode="live",          # or "shadow" to evaluate without executing
        target_system="mcp",
    )

    # Wrap a tool call:
    result = middleware.execute_tool(
        tool_name="send_email",
        tool_input={"to": "user@example.com", "body": "Hello"},
        proposed_by="my-mcp-agent",
    )
    # result -> {"receipt_id": ..., "decision": ..., "status": ..., "result": ...}

Shadow mode example::

    middleware = StatisMCPMiddleware(statis_client=client, mode="shadow")
    result = middleware.shadow_execute_tool(
        tool_name="delete_record",
        tool_input={"record_id": "abc123"},
    )
"""
from __future__ import annotations

from typing import Any, Optional

from .._models import ActionDeniedError, ActionEscalatedError


class StatisMCPMiddleware:
    """Wraps MCP tool calls through Statis governance.

    Each call to :meth:`execute_tool` runs the full Statis lifecycle:

    1. Propose — ``POST /actions`` with ``action_type=tool_name``,
       ``parameters=tool_input``.
    2. Evaluate — ``POST /actions/{id}/evaluate``.
    3. Wait — polls until a terminal status is reached.
    4. Return a result dict with receipt metadata.

    Parameters
    ----------
    statis_client:
        An initialised :class:`statis.StatisClient` instance.
    mode:
        ``"live"`` (default) executes the action after approval.
        ``"shadow"`` evaluates and receipts without touching any downstream
        system — safe for zero-risk piloting.
    target_system:
        Identifies the target system in the Statis receipt. Defaults to
        ``"mcp"``. Override if you want per-server granularity (e.g.
        ``"mcp:filesystem"``).
    """

    def __init__(
        self,
        statis_client: Any,
        mode: str = "live",
        target_system: str = "mcp",
    ) -> None:
        if mode not in ("live", "shadow"):
            raise ValueError(f"mode must be 'live' or 'shadow', got {mode!r}")
        self._client = statis_client
        self._mode = mode
        self._target_system = target_system

    # ------------------------------------------------------------------
    # Primary interface
    # ------------------------------------------------------------------

    def execute_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        proposed_by: str = "mcp-agent",
        timeout: Optional[float] = None,
        poll_interval: Optional[float] = None,
    ) -> dict[str, Any]:
        """Route an MCP tool call through Statis governance.

        Parameters
        ----------
        tool_name:
            The MCP tool name (e.g. ``"read_file"``, ``"send_email"``).
            Becomes the Statis ``action_type``.
        tool_input:
            The input dict passed to the MCP tool. Stored as the action
            ``parameters`` and included in the receipt.
        proposed_by:
            Agent identifier for the audit trail. Defaults to
            ``"mcp-agent"``.
        timeout:
            Maximum seconds to wait for a terminal status. ``None`` means
            wait indefinitely (inherits the client default).
        poll_interval:
            Override the client's polling interval (seconds).

        Returns
        -------
        dict
            ``{"receipt_id": str, "decision": str, "status": str,
            "result": dict | None}``

        Raises
        ------
        ActionDeniedError
            If the Statis policy engine denies the action.
        ActionEscalatedError
            If the action is escalated for human review.
        statis.StatisError
            On any API-level failure.
        """
        kwargs: dict[str, Any] = {}
        if timeout is not None:
            kwargs["timeout"] = timeout
        if poll_interval is not None:
            kwargs["poll_interval"] = poll_interval

        receipt = self._client.execute(
            action_type=tool_name,
            target={},                  # MCP tools are not entity-targeted
            parameters=tool_input,
            agent_id=proposed_by,
            target_system=self._target_system,
            **kwargs,
        )

        return {
            "receipt_id": receipt.receipt_id,
            "decision": receipt.decision,
            "status": "shadow_complete" if self._mode == "shadow" else "complete",
            "result": receipt.execution_result,
        }

    def shadow_execute_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        proposed_by: str = "mcp-agent",
        timeout: Optional[float] = None,
        poll_interval: Optional[float] = None,
    ) -> dict[str, Any]:
        """Convenience alias: govern the tool call in shadow mode.

        Equivalent to creating the middleware with ``mode="shadow"`` and
        calling :meth:`execute_tool`. The underlying client call is identical —
        this method forces ``mode`` to ``"shadow"`` for a single call
        regardless of how the middleware was initialised.

        Returns the same result dict as :meth:`execute_tool`.
        """
        # Temporarily swap mode if the instance is live
        original_mode = self._mode
        self._mode = "shadow"
        try:
            return self.execute_tool(
                tool_name=tool_name,
                tool_input=tool_input,
                proposed_by=proposed_by,
                timeout=timeout,
                poll_interval=poll_interval,
            )
        finally:
            self._mode = original_mode

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def mode(self) -> str:
        """Current execution mode: ``"live"`` or ``"shadow"``."""
        return self._mode

    @property
    def target_system(self) -> str:
        """Target system identifier used in receipts."""
        return self._target_system
