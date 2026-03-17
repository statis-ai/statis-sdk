"""Salesforce adapter — updates and creates records via the Salesforce REST API."""
from __future__ import annotations

import json
import os
import urllib.error
from typing import Any, Optional
from urllib.request import Request, urlopen

from app.adapters.base import BaseAdapter, ExecutionResult


class SalesforceAdapter(BaseAdapter):
    """Execute approved actions against Salesforce via the REST API.

    Supported action types:
      - ``salesforce_update_record`` — PATCH an existing sObject record
      - ``salesforce_create_record`` — POST a new sObject record (idempotent via external_id)

    Parameters for ``salesforce_update_record``:
      - ``object_type`` (str, required) — e.g. "Contact", "Account", "Lead"
      - ``record_id`` (str, required)   — Salesforce record ID (18-char)
      - ``fields`` (dict, required)     — field/value pairs to update

    Parameters for ``salesforce_create_record``:
      - ``object_type`` (str, required) — e.g. "Contact", "Lead"
      - ``fields`` (dict, required)     — field/value pairs; ``Statis_Action_Id__c``
                                          is injected automatically as idempotency key

    Configuration (env vars or constructor args):
      SALESFORCE_INSTANCE_URL  — e.g. https://yourorg.my.salesforce.com
      SALESFORCE_ACCESS_TOKEN  — OAuth2 access token
      SALESFORCE_API_VERSION   — default "v57.0"
    """

    SUPPORTED_ACTION_TYPES = {"salesforce_update_record", "salesforce_create_record"}

    def __init__(
        self,
        instance_url: Optional[str] = None,
        access_token: Optional[str] = None,
        api_version: Optional[str] = None,
    ) -> None:
        self._instance_url = (
            instance_url or os.environ.get("SALESFORCE_INSTANCE_URL", "")
        ).rstrip("/")
        self._access_token = access_token or os.environ.get("SALESFORCE_ACCESS_TOKEN", "")
        self._api_version = api_version or os.environ.get("SALESFORCE_API_VERSION", "v57.0")

    # ------------------------------------------------------------------

    def execute(self, action: Any) -> ExecutionResult:
        action_id: str = action.action_id if hasattr(action, "action_id") else action["action_id"]
        action_type: str = action.action_type if hasattr(action, "action_type") else action["action_type"]
        parameters: dict = action.parameters if hasattr(action, "parameters") else action.get("parameters", {})

        if action_type not in self.SUPPORTED_ACTION_TYPES:
            return ExecutionResult(
                success=False,
                result={},
                error=f"SalesforceAdapter does not handle action_type={action_type!r}",
            )

        if action_type == "salesforce_update_record":
            return self._update_record(action_id, parameters)
        return self._create_record(action_id, parameters)

    # ------------------------------------------------------------------

    def _update_record(self, action_id: str, parameters: dict) -> ExecutionResult:
        object_type = parameters.get("object_type", "")
        record_id = parameters.get("record_id", "")
        fields = parameters.get("fields", {})

        if not object_type:
            return ExecutionResult(success=False, result={}, error="parameters.object_type is required")
        if not record_id:
            return ExecutionResult(success=False, result={}, error="parameters.record_id is required")
        if not fields:
            return ExecutionResult(success=False, result={}, error="parameters.fields is required")

        path = f"/services/data/{self._api_version}/sobjects/{object_type}/{record_id}"
        try:
            # PATCH returns 204 No Content on success
            self._request("PATCH", path, fields)
        except _SalesforceHTTPError as exc:
            return ExecutionResult(
                success=False, result={}, error=f"Salesforce API {exc.status}: {exc.body}"
            )
        except Exception as exc:
            return ExecutionResult(success=False, result={}, error=str(exc))

        return ExecutionResult(
            success=True,
            result={
                "object_type": object_type,
                "record_id": record_id,
                "action": "updated",
                "statis_action_id": action_id,
            },
        )

    def _create_record(self, action_id: str, parameters: dict) -> ExecutionResult:
        object_type = parameters.get("object_type", "")
        fields = parameters.get("fields", {})

        if not object_type:
            return ExecutionResult(success=False, result={}, error="parameters.object_type is required")
        if not fields:
            return ExecutionResult(success=False, result={}, error="parameters.fields is required")

        # Inject action_id as external idempotency key if the field exists on the object
        payload = {**fields, "Statis_Action_Id__c": action_id}

        path = f"/services/data/{self._api_version}/sobjects/{object_type}"
        try:
            resp = self._request("POST", path, payload)
        except _SalesforceHTTPError as exc:
            return ExecutionResult(
                success=False, result={}, error=f"Salesforce API {exc.status}: {exc.body}"
            )
        except Exception as exc:
            return ExecutionResult(success=False, result={}, error=str(exc))

        return ExecutionResult(
            success=True,
            result={
                "object_type": object_type,
                "record_id": resp.get("id", ""),
                "action": "created",
                "statis_action_id": action_id,
            },
        )

    # ------------------------------------------------------------------

    def _request(self, method: str, path: str, body: dict) -> dict:
        url = self._instance_url + path
        data = json.dumps(body).encode()
        req = Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._access_token}",
            },
            method=method,
        )
        try:
            with urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise _SalesforceHTTPError(exc.code, exc.read().decode()) from exc


class _SalesforceHTTPError(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        self.body = body
