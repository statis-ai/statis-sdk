"""Linear adapter — manages issues via the Linear GraphQL API."""
from __future__ import annotations

import json
import os
import urllib.error
from typing import Any, Optional
from urllib.request import Request, urlopen

from .base import BaseAdapter, ExecutionResult

_GRAPHQL_URL = "https://api.linear.app/graphql"


class LinearAdapter(BaseAdapter):
    """Execute approved actions against Linear via the GraphQL API.

    Supported action types:
      - ``create_issue``  — Create a new issue in a team
      - ``update_issue``  — Update title, description, or status of an issue
      - ``assign_issue``  — Assign an issue to a team member
      - ``close_issue``   — Close an issue by setting it to a done state

    Parameters for ``create_issue``:
      - ``title`` (str, required)
      - ``teamId`` (str, required)
      - ``description`` (str, optional)

    Parameters for ``update_issue``:
      - ``id`` (str, required)          — Linear issue ID
      - ``title`` (str, optional)
      - ``description`` (str, optional)
      - ``status`` (str, optional)      — state name (e.g. "In Progress")

    Parameters for ``assign_issue``:
      - ``id`` (str, required)
      - ``assigneeId`` (str, required)  — Linear user ID

    Parameters for ``close_issue``:
      - ``id`` (str, required)
      - ``stateId`` (str, required)     — ID of the done/closed state

    Configuration:
      LINEAR_API_KEY  — Linear personal API key (set in env or pass to constructor)
    """

    SUPPORTED_ACTION_TYPES = {"create_issue", "update_issue", "assign_issue", "close_issue"}

    def __init__(self, api_key: Optional[str] = None) -> None:
        resolved = api_key or os.environ.get("LINEAR_API_KEY", "")
        if not resolved:
            raise ValueError(
                "LINEAR_API_KEY is required. Set the environment variable or pass "
                "api_key= to LinearAdapter()."
            )
        self._api_key = resolved

    # ------------------------------------------------------------------

    def execute(self, action: Any) -> ExecutionResult:
        action_id: str = action.action_id if hasattr(action, "action_id") else action["action_id"]
        action_type: str = action.action_type if hasattr(action, "action_type") else action["action_type"]
        parameters: dict = action.parameters if hasattr(action, "parameters") else action.get("parameters", {})

        if action_type not in self.SUPPORTED_ACTION_TYPES:
            return ExecutionResult(
                success=False,
                result={},
                error=f"LinearAdapter does not handle action_type={action_type!r}",
            )

        dispatch = {
            "create_issue": self._create_issue,
            "update_issue": self._update_issue,
            "assign_issue": self._assign_issue,
            "close_issue": self._close_issue,
        }
        return dispatch[action_type](action_id, parameters)

    # ------------------------------------------------------------------
    # Action implementations
    # ------------------------------------------------------------------

    def _create_issue(self, action_id: str, parameters: dict) -> ExecutionResult:
        title = parameters.get("title", "")
        team_id = parameters.get("teamId", "")

        if not title:
            return ExecutionResult(success=False, result={}, error="parameters.title is required")
        if not team_id:
            return ExecutionResult(success=False, result={}, error="parameters.teamId is required")

        input_fields: dict[str, Any] = {"title": title, "teamId": team_id}
        if parameters.get("description"):
            input_fields["description"] = parameters["description"]

        query = """
        mutation CreateIssue($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue {
                    id
                    title
                    url
                }
            }
        }
        """
        try:
            data = self._graphql(query, {"input": input_fields})
        except _LinearHTTPError as exc:
            return ExecutionResult(success=False, result={}, error=f"Linear API {exc.status}: {exc.body}")
        except Exception as exc:
            return ExecutionResult(success=False, result={}, error=str(exc))

        issue = data.get("issueCreate", {}).get("issue", {})
        return ExecutionResult(
            success=True,
            result={
                "id": issue.get("id"),
                "title": issue.get("title"),
                "url": issue.get("url"),
                "action": "created",
                "statis_action_id": action_id,
            },
        )

    def _update_issue(self, action_id: str, parameters: dict) -> ExecutionResult:
        issue_id = parameters.get("id", "")
        if not issue_id:
            return ExecutionResult(success=False, result={}, error="parameters.id is required")

        input_fields: dict[str, Any] = {}
        for field in ("title", "description", "status"):
            if parameters.get(field) is not None:
                input_fields[field] = parameters[field]

        if not input_fields:
            return ExecutionResult(
                success=False,
                result={},
                error="At least one of title, description, or status is required",
            )

        query = """
        mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
            issueUpdate(id: $id, input: $input) {
                success
                issue {
                    id
                    title
                    url
                }
            }
        }
        """
        try:
            data = self._graphql(query, {"id": issue_id, "input": input_fields})
        except _LinearHTTPError as exc:
            return ExecutionResult(success=False, result={}, error=f"Linear API {exc.status}: {exc.body}")
        except Exception as exc:
            return ExecutionResult(success=False, result={}, error=str(exc))

        issue = data.get("issueUpdate", {}).get("issue", {})
        return ExecutionResult(
            success=True,
            result={
                "id": issue.get("id", issue_id),
                "action": "updated",
                "updated_fields": list(input_fields.keys()),
                "statis_action_id": action_id,
            },
        )

    def _assign_issue(self, action_id: str, parameters: dict) -> ExecutionResult:
        issue_id = parameters.get("id", "")
        assignee_id = parameters.get("assigneeId", "")

        if not issue_id:
            return ExecutionResult(success=False, result={}, error="parameters.id is required")
        if not assignee_id:
            return ExecutionResult(success=False, result={}, error="parameters.assigneeId is required")

        query = """
        mutation AssignIssue($id: String!, $input: IssueUpdateInput!) {
            issueUpdate(id: $id, input: $input) {
                success
                issue {
                    id
                    url
                }
            }
        }
        """
        try:
            data = self._graphql(query, {"id": issue_id, "input": {"assigneeId": assignee_id}})
        except _LinearHTTPError as exc:
            return ExecutionResult(success=False, result={}, error=f"Linear API {exc.status}: {exc.body}")
        except Exception as exc:
            return ExecutionResult(success=False, result={}, error=str(exc))

        issue = data.get("issueUpdate", {}).get("issue", {})
        return ExecutionResult(
            success=True,
            result={
                "id": issue.get("id", issue_id),
                "assigneeId": assignee_id,
                "action": "assigned",
                "statis_action_id": action_id,
            },
        )

    def _close_issue(self, action_id: str, parameters: dict) -> ExecutionResult:
        issue_id = parameters.get("id", "")
        state_id = parameters.get("stateId", "")

        if not issue_id:
            return ExecutionResult(success=False, result={}, error="parameters.id is required")
        if not state_id:
            return ExecutionResult(success=False, result={}, error="parameters.stateId is required")

        query = """
        mutation CloseIssue($id: String!, $input: IssueUpdateInput!) {
            issueUpdate(id: $id, input: $input) {
                success
                issue {
                    id
                    url
                }
            }
        }
        """
        try:
            data = self._graphql(query, {"id": issue_id, "input": {"stateId": state_id}})
        except _LinearHTTPError as exc:
            return ExecutionResult(success=False, result={}, error=f"Linear API {exc.status}: {exc.body}")
        except Exception as exc:
            return ExecutionResult(success=False, result={}, error=str(exc))

        issue = data.get("issueUpdate", {}).get("issue", {})
        return ExecutionResult(
            success=True,
            result={
                "id": issue.get("id", issue_id),
                "stateId": state_id,
                "action": "closed",
                "statis_action_id": action_id,
            },
        )

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _graphql(self, query: str, variables: dict) -> dict:
        payload = json.dumps({"query": query, "variables": variables}).encode()
        req = Request(
            _GRAPHQL_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=30) as resp:
                raw = resp.read()
                body = json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise _LinearHTTPError(exc.code, exc.read().decode()) from exc

        if "errors" in body:
            raise _LinearHTTPError(200, json.dumps(body["errors"]))

        return body.get("data", {})


class _LinearHTTPError(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        self.body = body
