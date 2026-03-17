"""Airflow adapter — triggers DAG runs via the Airflow stable REST API (v1)."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.request import Request, urlopen
import json
import urllib.error

from app.adapters.base import BaseAdapter, ExecutionResult


class AirflowAdapter(BaseAdapter):
    """Trigger Airflow DAG runs for approved actions.

    The action contract must have:
      - ``action_type``: ``"airflow_dag_trigger"``
      - ``parameters.dag_id``: the DAG to trigger
      - ``parameters.conf``: optional dict passed as DAG run conf
      - ``parameters.logical_date``: optional ISO-8601 string

    The action_id is used as ``dag_run_id`` — Airflow will reject a duplicate
    run id, making this naturally idempotent.

    Configuration (env vars or constructor args):
      AIRFLOW_BASE_URL  — e.g. https://airflow.internal
      AIRFLOW_USERNAME  — basic-auth username
      AIRFLOW_PASSWORD  — basic-auth password
    """

    SUPPORTED_ACTION_TYPES = {"airflow_dag_trigger"}

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        self._base_url = (base_url or os.environ.get("AIRFLOW_BASE_URL", "")).rstrip("/")
        self._username = username or os.environ.get("AIRFLOW_USERNAME", "")
        self._password = password or os.environ.get("AIRFLOW_PASSWORD", "")

    # ------------------------------------------------------------------

    def execute(self, action: Any) -> ExecutionResult:
        action_id: str = (
            action.action_id if hasattr(action, "action_id") else action["action_id"]
        )
        action_type: str = (
            action.action_type if hasattr(action, "action_type") else action["action_type"]
        )
        parameters: dict = (
            action.parameters if hasattr(action, "parameters") else action.get("parameters", {})
        )

        if action_type not in self.SUPPORTED_ACTION_TYPES:
            return ExecutionResult(
                success=False,
                result={},
                error=f"AirflowAdapter does not handle action_type={action_type!r}",
            )

        dag_id: str = parameters.get("dag_id", "")
        if not dag_id:
            return ExecutionResult(
                success=False,
                result={},
                error="parameters.dag_id is required for airflow_dag_trigger",
            )

        logical_date: str = parameters.get(
            "logical_date",
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        )
        conf: dict = parameters.get("conf") or {}

        payload = {
            "dag_run_id": action_id,          # idempotency key
            "logical_date": logical_date,
            "conf": conf,
        }

        try:
            resp_body = self._post(
                f"/api/v1/dags/{dag_id}/dagRuns",
                payload,
            )
        except _AirflowHTTPError as exc:
            # 409 = dag_run_id already exists → idempotent success
            if exc.status == 409:
                return ExecutionResult(
                    success=True,
                    result={
                        "dag_run_id": action_id,
                        "dag_id": dag_id,
                        "state": "already_exists",
                        "logical_date": logical_date,
                    },
                )
            return ExecutionResult(
                success=False,
                result={},
                error=f"Airflow API {exc.status}: {exc.body}",
            )
        except Exception as exc:  # network errors, misconfiguration
            return ExecutionResult(
                success=False,
                result={},
                error=str(exc),
            )

        return ExecutionResult(
            success=True,
            result={
                "dag_run_id": resp_body.get("dag_run_id", action_id),
                "dag_id": resp_body.get("dag_id", dag_id),
                "state": resp_body.get("state", "queued"),
                "logical_date": resp_body.get("logical_date", logical_date),
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _post(self, path: str, body: dict) -> dict:
        import base64

        url = self._base_url + path
        data = json.dumps(body).encode()
        credentials = base64.b64encode(
            f"{self._username}:{self._password}".encode()
        ).decode()

        req = Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {credentials}",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raise _AirflowHTTPError(exc.code, exc.read().decode()) from exc


class _AirflowHTTPError(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        self.body = body
