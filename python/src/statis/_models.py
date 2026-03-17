from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class Receipt:
    receipt_id: str
    action_id: str
    decision: str
    rule_id: Optional[str]
    rule_version: Optional[str]
    approved_by: str
    conditions_evaluated: Optional[dict[str, Any]]
    execution_result: Optional[dict[str, Any]]
    executed_at: Optional[datetime]
    hash: str
    created_at: datetime


class StatisError(Exception):
    """Raised when the Statis API returns a non-2xx response."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message


class ActionDeniedError(Exception):
    """Raised by execute() when the policy engine denies the action."""

    def __init__(self, reason: str, receipt: Receipt) -> None:
        super().__init__(reason)
        self.reason = reason
        self.receipt = receipt


class ActionTimeoutError(Exception):
    """Raised by execute() when execution doesn't complete within timeout."""

    def __init__(self, action_id: str, timeout: float) -> None:
        super().__init__(
            f"Action '{action_id}' did not complete within {timeout}s"
        )
        self.action_id = action_id
        self.timeout = timeout


class ActionEscalatedError(Exception):
    """Raised by execute() when the policy engine escalates the action for human review.

    The agent should surface this to its operator and stop waiting — a human
    must approve or reject via the Statis Console (or API) before execution proceeds.
    """

    def __init__(self, action_id: str) -> None:
        super().__init__(
            f"Action '{action_id}' was escalated and requires human review"
        )
        self.action_id = action_id
