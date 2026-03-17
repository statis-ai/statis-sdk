"""HubSpot adapter — updates contacts and creates deals via the HubSpot CRM API v3."""
from __future__ import annotations

import json
import os
import urllib.error
from typing import Any, Optional
from urllib.request import Request, urlopen

from app.adapters.base import BaseAdapter, ExecutionResult

_BASE_URL = "https://api.hubapi.com"


class HubSpotAdapter(BaseAdapter):
    """Execute approved actions against HubSpot via the CRM API v3.

    Supported action types:
      - ``hubspot_update_contact`` — PATCH contact properties (idempotent)
      - ``hubspot_create_deal``    — POST a new deal (idempotent via hs_unique_creation_key = action_id)

    Parameters for ``hubspot_update_contact``:
      - ``contact_id`` (str, required)   — HubSpot contact ID or email (via idProperty)
      - ``properties`` (dict, required)  — HubSpot property name/value pairs

    Parameters for ``hubspot_create_deal``:
      - ``deal_name`` (str, required)
      - ``pipeline`` (str, required)     — pipeline ID
      - ``stage`` (str, required)        — deal stage ID
      - ``amount`` (float, optional)
      - ``contact_id`` (str, optional)   — associate deal with a contact

    Configuration (env vars or constructor args):
      HUBSPOT_ACCESS_TOKEN  — private app access token (starts with pat-)
    """

    SUPPORTED_ACTION_TYPES = {"hubspot_update_contact", "hubspot_create_deal"}

    def __init__(self, access_token: Optional[str] = None) -> None:
        self._access_token = access_token or os.environ.get("HUBSPOT_ACCESS_TOKEN", "")

    # ------------------------------------------------------------------

    def execute(self, action: Any) -> ExecutionResult:
        action_id: str = action.action_id if hasattr(action, "action_id") else action["action_id"]
        action_type: str = action.action_type if hasattr(action, "action_type") else action["action_type"]
        parameters: dict = action.parameters if hasattr(action, "parameters") else action.get("parameters", {})

        if action_type not in self.SUPPORTED_ACTION_TYPES:
            return ExecutionResult(
                success=False,
                result={},
                error=f"HubSpotAdapter does not handle action_type={action_type!r}",
            )

        if action_type == "hubspot_update_contact":
            return self._update_contact(action_id, parameters)
        return self._create_deal(action_id, parameters)

    # ------------------------------------------------------------------

    def _update_contact(self, action_id: str, parameters: dict) -> ExecutionResult:
        contact_id = parameters.get("contact_id", "")
        properties = parameters.get("properties", {})

        if not contact_id:
            return ExecutionResult(success=False, result={}, error="parameters.contact_id is required")
        if not properties:
            return ExecutionResult(success=False, result={}, error="parameters.properties is required")

        payload = {"properties": properties}
        try:
            resp = self._request("PATCH", f"/crm/v3/objects/contacts/{contact_id}", payload)
        except _HubSpotHTTPError as exc:
            return ExecutionResult(
                success=False, result={}, error=f"HubSpot API {exc.status}: {exc.body}"
            )
        except Exception as exc:
            return ExecutionResult(success=False, result={}, error=str(exc))

        return ExecutionResult(
            success=True,
            result={
                "contact_id": resp.get("id", contact_id),
                "action": "updated",
                "updated_properties": list(properties.keys()),
                "statis_action_id": action_id,
            },
        )

    def _create_deal(self, action_id: str, parameters: dict) -> ExecutionResult:
        deal_name = parameters.get("deal_name", "")
        pipeline = parameters.get("pipeline", "")
        stage = parameters.get("stage", "")

        if not deal_name:
            return ExecutionResult(success=False, result={}, error="parameters.deal_name is required")
        if not pipeline:
            return ExecutionResult(success=False, result={}, error="parameters.pipeline is required")
        if not stage:
            return ExecutionResult(success=False, result={}, error="parameters.stage is required")

        properties: dict[str, Any] = {
            "dealname": deal_name,
            "pipeline": pipeline,
            "dealstage": stage,
            "hs_unique_creation_key": action_id,  # idempotency key
        }
        if parameters.get("amount") is not None:
            properties["amount"] = str(parameters["amount"])

        payload: dict[str, Any] = {"properties": properties}

        # Associate with contact if provided
        contact_id = parameters.get("contact_id")
        if contact_id:
            payload["associations"] = [
                {
                    "to": {"id": contact_id},
                    "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 3}],
                }
            ]

        try:
            resp = self._request("POST", "/crm/v3/objects/deals", payload)
        except _HubSpotHTTPError as exc:
            # 409 = hs_unique_creation_key conflict → idempotent
            if exc.status == 409:
                return ExecutionResult(
                    success=True,
                    result={
                        "deal_name": deal_name,
                        "action": "already_exists",
                        "statis_action_id": action_id,
                    },
                )
            return ExecutionResult(
                success=False, result={}, error=f"HubSpot API {exc.status}: {exc.body}"
            )
        except Exception as exc:
            return ExecutionResult(success=False, result={}, error=str(exc))

        return ExecutionResult(
            success=True,
            result={
                "deal_id": resp.get("id"),
                "deal_name": deal_name,
                "pipeline": pipeline,
                "stage": stage,
                "action": "created",
                "statis_action_id": action_id,
            },
        )

    # ------------------------------------------------------------------

    def _request(self, method: str, path: str, body: dict) -> dict:
        url = _BASE_URL + path
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
            raise _HubSpotHTTPError(exc.code, exc.read().decode()) from exc


class _HubSpotHTTPError(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        self.body = body
