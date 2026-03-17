"""Zendesk adapter — creates and updates support tickets via the Zendesk REST API."""
from __future__ import annotations

import base64
import json
import os
import urllib.error
from typing import Any, Optional
from urllib.request import Request, urlopen

from app.adapters.base import BaseAdapter, ExecutionResult


class ZendeskAdapter(BaseAdapter):
    """Execute approved actions against Zendesk via the REST API v2.

    Supported action types:
      - ``zendesk_create_ticket`` — Create a new ticket (idempotent via external_id = action_id)
      - ``zendesk_update_ticket`` — Update an existing ticket's status or add a comment

    Parameters for ``zendesk_create_ticket``:
      - ``subject`` (str, required)
      - ``body`` (str, required)       — ticket description
      - ``requester_email`` (str, required)
      - ``priority`` (str, optional)   — "urgent" | "high" | "normal" | "low"
      - ``tags`` (list, optional)

    Parameters for ``zendesk_update_ticket``:
      - ``ticket_id`` (int, required)
      - ``status`` (str, optional)     — "open" | "pending" | "solved" | "closed"
      - ``comment`` (str, optional)    — appends a comment to the ticket

    Configuration (env vars or constructor args):
      ZENDESK_SUBDOMAIN   — e.g. "yourcompany" (not the full URL)
      ZENDESK_EMAIL       — agent email address
      ZENDESK_API_TOKEN   — API token from Zendesk Admin › Apps & Integrations › APIs
    """

    SUPPORTED_ACTION_TYPES = {"zendesk_create_ticket", "zendesk_update_ticket"}

    def __init__(
        self,
        subdomain: Optional[str] = None,
        email: Optional[str] = None,
        api_token: Optional[str] = None,
    ) -> None:
        self._subdomain = subdomain or os.environ.get("ZENDESK_SUBDOMAIN", "")
        self._email = email or os.environ.get("ZENDESK_EMAIL", "")
        self._api_token = api_token or os.environ.get("ZENDESK_API_TOKEN", "")

    @property
    def _base_url(self) -> str:
        return f"https://{self._subdomain}.zendesk.com"

    @property
    def _auth_header(self) -> str:
        credentials = f"{self._email}/token:{self._api_token}"
        return "Basic " + base64.b64encode(credentials.encode()).decode()

    # ------------------------------------------------------------------

    def execute(self, action: Any) -> ExecutionResult:
        action_id: str = action.action_id if hasattr(action, "action_id") else action["action_id"]
        action_type: str = action.action_type if hasattr(action, "action_type") else action["action_type"]
        parameters: dict = action.parameters if hasattr(action, "parameters") else action.get("parameters", {})

        if action_type not in self.SUPPORTED_ACTION_TYPES:
            return ExecutionResult(
                success=False,
                result={},
                error=f"ZendeskAdapter does not handle action_type={action_type!r}",
            )

        if action_type == "zendesk_create_ticket":
            return self._create_ticket(action_id, parameters)
        return self._update_ticket(action_id, parameters)

    # ------------------------------------------------------------------

    def _create_ticket(self, action_id: str, parameters: dict) -> ExecutionResult:
        subject = parameters.get("subject", "")
        body = parameters.get("body", "")
        requester_email = parameters.get("requester_email", "")

        if not subject:
            return ExecutionResult(success=False, result={}, error="parameters.subject is required")
        if not body:
            return ExecutionResult(success=False, result={}, error="parameters.body is required")
        if not requester_email:
            return ExecutionResult(success=False, result={}, error="parameters.requester_email is required")

        payload: dict[str, Any] = {
            "ticket": {
                "external_id": action_id,       # idempotency key
                "subject": subject,
                "comment": {"body": body},
                "requester": {"email": requester_email},
            }
        }
        if parameters.get("priority"):
            payload["ticket"]["priority"] = parameters["priority"]
        if parameters.get("tags"):
            payload["ticket"]["tags"] = parameters["tags"]

        try:
            resp = self._request("POST", "/api/v2/tickets", payload)
        except _ZendeskHTTPError as exc:
            return ExecutionResult(
                success=False, result={}, error=f"Zendesk API {exc.status}: {exc.body}"
            )
        except Exception as exc:
            return ExecutionResult(success=False, result={}, error=str(exc))

        ticket = resp.get("ticket", {})
        return ExecutionResult(
            success=True,
            result={
                "ticket_id": ticket.get("id"),
                "ticket_url": f"{self._base_url}/agent/tickets/{ticket.get('id')}",
                "external_id": action_id,
                "status": ticket.get("status", "new"),
            },
        )

    def _update_ticket(self, action_id: str, parameters: dict) -> ExecutionResult:
        ticket_id = parameters.get("ticket_id")
        if not ticket_id:
            return ExecutionResult(success=False, result={}, error="parameters.ticket_id is required")

        ticket_body: dict[str, Any] = {}
        if parameters.get("status"):
            ticket_body["status"] = parameters["status"]
        if parameters.get("comment"):
            ticket_body["comment"] = {"body": parameters["comment"], "public": True}

        if not ticket_body:
            return ExecutionResult(success=False, result={}, error="At least one of: status, comment is required")

        payload = {"ticket": ticket_body}
        try:
            resp = self._request("PUT", f"/api/v2/tickets/{ticket_id}", payload)
        except _ZendeskHTTPError as exc:
            return ExecutionResult(
                success=False, result={}, error=f"Zendesk API {exc.status}: {exc.body}"
            )
        except Exception as exc:
            return ExecutionResult(success=False, result={}, error=str(exc))

        ticket = resp.get("ticket", {})
        return ExecutionResult(
            success=True,
            result={
                "ticket_id": ticket.get("id", ticket_id),
                "ticket_url": f"{self._base_url}/agent/tickets/{ticket_id}",
                "status": ticket.get("status"),
                "statis_action_id": action_id,
            },
        )

    # ------------------------------------------------------------------

    def _request(self, method: str, path: str, body: dict) -> dict:
        url = self._base_url + path
        data = json.dumps(body).encode()
        req = Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": self._auth_header,
            },
            method=method,
        )
        try:
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raise _ZendeskHTTPError(exc.code, exc.read().decode()) from exc


class _ZendeskHTTPError(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        self.body = body
