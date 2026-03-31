"""GitHub Actions adapter — triggers and cancels workflow runs via the GitHub REST API."""
from __future__ import annotations

import json
import os
import urllib.error
from typing import Any, Optional
from urllib.request import Request, urlopen

from .base import BaseAdapter, ExecutionResult

_BASE_URL = "https://api.github.com"


class GitHubActionsAdapter(BaseAdapter):
    """Execute approved actions against GitHub Actions via the REST API.

    Supported action types:
      - ``trigger_workflow``      — Dispatch a workflow run (workflow_dispatch event)
      - ``cancel_workflow_run``   — Cancel an in-progress workflow run

    Parameters for ``trigger_workflow``:
      - ``owner`` (str, required)       — GitHub org or username
      - ``repo`` (str, required)        — Repository name
      - ``workflow_id`` (str, required) — Workflow file name (e.g. "deploy.yml") or workflow ID
      - ``ref`` (str, optional)         — Branch or tag ref to run against. Default: "main"
      - ``inputs`` (dict, optional)     — Workflow dispatch inputs. Default: {}

    Parameters for ``cancel_workflow_run``:
      - ``owner`` (str, required)
      - ``repo`` (str, required)
      - ``run_id`` (str/int, required)  — Workflow run ID

    Configuration:
      GITHUB_TOKEN  — GitHub personal access token or Actions token
    """

    SUPPORTED_ACTION_TYPES = {"trigger_workflow", "cancel_workflow_run"}

    def __init__(self, token: Optional[str] = None) -> None:
        resolved = token or os.environ.get("GITHUB_TOKEN", "")
        if not resolved:
            raise ValueError(
                "GITHUB_TOKEN is required. Set the environment variable or pass "
                "token= to GitHubActionsAdapter()."
            )
        self._token = resolved

    # ------------------------------------------------------------------

    def execute(self, action: Any) -> ExecutionResult:
        action_id: str = action.action_id if hasattr(action, "action_id") else action["action_id"]
        action_type: str = action.action_type if hasattr(action, "action_type") else action["action_type"]
        parameters: dict = action.parameters if hasattr(action, "parameters") else action.get("parameters", {})

        if action_type not in self.SUPPORTED_ACTION_TYPES:
            return ExecutionResult(
                success=False,
                result={},
                error=f"GitHubActionsAdapter does not handle action_type={action_type!r}",
            )

        if action_type == "trigger_workflow":
            return self._trigger_workflow(action_id, parameters)
        return self._cancel_workflow_run(action_id, parameters)

    # ------------------------------------------------------------------

    def _trigger_workflow(self, action_id: str, parameters: dict) -> ExecutionResult:
        owner = parameters.get("owner", "")
        repo = parameters.get("repo", "")
        workflow_id = parameters.get("workflow_id", "")
        ref = parameters.get("ref", "main")
        inputs = parameters.get("inputs", {})

        if not owner:
            return ExecutionResult(success=False, result={}, error="parameters.owner is required")
        if not repo:
            return ExecutionResult(success=False, result={}, error="parameters.repo is required")
        if not workflow_id:
            return ExecutionResult(success=False, result={}, error="parameters.workflow_id is required")

        path = f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches"
        body: dict[str, Any] = {"ref": ref, "inputs": inputs}

        try:
            # Returns 204 No Content on success
            self._request("POST", path, body, expect_body=False)
        except _GitHubHTTPError as exc:
            return ExecutionResult(
                success=False,
                result={},
                error=f"GitHub API {exc.status}: {exc.body}",
            )
        except Exception as exc:
            return ExecutionResult(success=False, result={}, error=str(exc))

        return ExecutionResult(
            success=True,
            result={
                "owner": owner,
                "repo": repo,
                "workflow_id": workflow_id,
                "ref": ref,
                "inputs": inputs,
                "action": "workflow_dispatched",
                "statis_action_id": action_id,
            },
        )

    def _cancel_workflow_run(self, action_id: str, parameters: dict) -> ExecutionResult:
        owner = parameters.get("owner", "")
        repo = parameters.get("repo", "")
        run_id = parameters.get("run_id", "")

        if not owner:
            return ExecutionResult(success=False, result={}, error="parameters.owner is required")
        if not repo:
            return ExecutionResult(success=False, result={}, error="parameters.repo is required")
        if not run_id:
            return ExecutionResult(success=False, result={}, error="parameters.run_id is required")

        path = f"/repos/{owner}/{repo}/actions/runs/{run_id}/cancel"

        try:
            # Returns 202 Accepted on success
            self._request("POST", path, {}, expect_body=False)
        except _GitHubHTTPError as exc:
            return ExecutionResult(
                success=False,
                result={},
                error=f"GitHub API {exc.status}: {exc.body}",
            )
        except Exception as exc:
            return ExecutionResult(success=False, result={}, error=str(exc))

        return ExecutionResult(
            success=True,
            result={
                "owner": owner,
                "repo": repo,
                "run_id": str(run_id),
                "action": "workflow_run_cancelled",
                "statis_action_id": action_id,
            },
        )

    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        body: dict,
        expect_body: bool = True,
    ) -> dict:
        url = _BASE_URL + path
        data = json.dumps(body).encode() if body else b""
        req = Request(
            url,
            data=data if data else None,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method=method,
        )
        try:
            with urlopen(req, timeout=30) as resp:
                if not expect_body:
                    return {}
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise _GitHubHTTPError(exc.code, exc.read().decode()) from exc


class _GitHubHTTPError(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        self.body = body
