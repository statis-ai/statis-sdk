"""Adapter base — defines the contract all execution adapters must satisfy."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ExecutionResult:
    success: bool
    result: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class BaseAdapter(ABC):
    """Execute an approved action against an external system.

    Implementations must be idempotent — the same action_id must always
    produce the same outcome if re-executed (e.g. use the action_id as an
    idempotency key in the downstream API call).
    """

    @abstractmethod
    def execute(self, action: Any) -> ExecutionResult: ...
