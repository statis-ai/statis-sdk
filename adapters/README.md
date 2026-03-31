# Statis Adapters

Adapters execute approved actions against external systems. Each adapter receives a Statis action object (after policy evaluation and approval) and calls the relevant downstream API.

All adapters live in `adapters/python/` and implement the `BaseAdapter` interface.

---

## Available Adapters

| Adapter | Class | Action Types | Required Env Vars |
|---------|-------|--------------|-------------------|
| [Airflow](python/airflow.py) | `AirflowAdapter` | `airflow_dag_trigger` | `AIRFLOW_BASE_URL`, `AIRFLOW_USERNAME`, `AIRFLOW_PASSWORD` |
| [GitHub Actions](python/github_actions.py) | `GitHubActionsAdapter` | `trigger_workflow`, `cancel_workflow_run` | `GITHUB_TOKEN` |
| [HubSpot](python/hubspot.py) | `HubSpotAdapter` | `hubspot_update_contact`, `hubspot_create_deal` | `HUBSPOT_ACCESS_TOKEN` |
| [Linear](python/linear.py) | `LinearAdapter` | `create_issue`, `update_issue`, `assign_issue`, `close_issue` | `LINEAR_API_KEY` |
| [Salesforce](python/salesforce.py) | `SalesforceAdapter` | `salesforce_update_record`, `salesforce_create_record` | `SALESFORCE_INSTANCE_URL`, `SALESFORCE_ACCESS_TOKEN` |
| [Slack](python/slack.py) | `SlackAdapter` | `send_message`, `post_to_channel` | `SLACK_BOT_TOKEN` |
| [Stripe (mock)](python/stripe_mock.py) | `MockStripeAdapter` | `apply_discount`, `retention_offer` | none (mock only) |
| [Zendesk](python/zendesk.py) | `ZendeskAdapter` | `zendesk_create_ticket`, `zendesk_update_ticket` | `ZENDESK_SUBDOMAIN`, `ZENDESK_EMAIL`, `ZENDESK_API_TOKEN` |

---

## Writing a Custom Adapter

### BaseAdapter interface

```python
# adapters/python/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class ExecutionResult:
    success: bool
    result: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

class BaseAdapter(ABC):
    @abstractmethod
    def execute(self, action: Any) -> ExecutionResult: ...
```

`execute` receives an action object (or dict) with at minimum:

- `action_id` — unique ID for idempotency
- `action_type` — string that selects which operation to perform
- `parameters` — dict of operation-specific arguments

### Minimal example

```python
"""my_service.py — Adapter for MyService."""
from __future__ import annotations

import os
from typing import Any, Optional

from .base import BaseAdapter, ExecutionResult


class MyServiceAdapter(BaseAdapter):
    """Execute approved actions against MyService.

    Supported action types:
      - ``my_service_do_thing`` — Does the thing

    Parameters for ``my_service_do_thing``:
      - ``resource_id`` (str, required)
      - ``value`` (str, required)

    Configuration:
      MY_SERVICE_API_KEY  — API key for MyService
    """

    SUPPORTED_ACTION_TYPES = {"my_service_do_thing"}

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key or os.environ.get("MY_SERVICE_API_KEY", "")
        if not self._api_key:
            raise ValueError("MY_SERVICE_API_KEY is required")

    def execute(self, action: Any) -> ExecutionResult:
        action_id: str = action.action_id if hasattr(action, "action_id") else action["action_id"]
        action_type: str = action.action_type if hasattr(action, "action_type") else action["action_type"]
        parameters: dict = action.parameters if hasattr(action, "parameters") else action.get("parameters", {})

        if action_type not in self.SUPPORTED_ACTION_TYPES:
            return ExecutionResult(
                success=False,
                result={},
                error=f"MyServiceAdapter does not handle action_type={action_type!r}",
            )

        resource_id = parameters.get("resource_id", "")
        value = parameters.get("value", "")

        if not resource_id:
            return ExecutionResult(success=False, result={}, error="parameters.resource_id is required")
        if not value:
            return ExecutionResult(success=False, result={}, error="parameters.value is required")

        # Call your API here ...
        # resp = self._call_api(resource_id, value)

        return ExecutionResult(
            success=True,
            result={
                "resource_id": resource_id,
                "action": "done",
                "statis_action_id": action_id,  # always echo this back
            },
        )
```

### Rules

1. **Always use `action_id` as an idempotency key** when the downstream API supports it (e.g. as an external reference or deduplication header). The same action may be retried.
2. **Return `ExecutionResult(success=False, error=...)` for recoverable errors** — do not raise exceptions from `execute`. The Statis worker handles the error and updates the receipt.
3. **Raise `ValueError` in `__init__`** if required credentials are missing. Fail fast at construction, not at runtime.
4. **Keep `SUPPORTED_ACTION_TYPES` explicit** and return an error for unrecognised types rather than silently doing nothing.
5. **Register your adapter** in `adapters/python/__init__.py` so it can be imported via the package.
