"""Slack adapter — sends messages via the Slack Web API."""
from __future__ import annotations

import json
import os
import urllib.error
from typing import Any, List, Optional
from urllib.request import Request, urlopen

from .base import BaseAdapter, ExecutionResult

_CHAT_POST_URL = "https://slack.com/api/chat.postMessage"


class SlackAdapter(BaseAdapter):
    """Execute approved actions against Slack via the Web API.

    Supported action types:
      - ``send_message``      — Send a message to a Slack channel or user
      - ``post_to_channel``   — Alias for send_message; both call chat.postMessage

    Parameters for both action types:
      - ``channel`` (str, required)   — Channel ID, channel name (e.g. "#general"),
                                        or user ID for a DM
      - ``text`` (str, required)      — Message text (plain text or mrkdwn)
      - ``blocks`` (list, optional)   — Slack Block Kit blocks to attach

    Configuration:
      SLACK_BOT_TOKEN  — Bot OAuth token (xoxb-...)
    """

    SUPPORTED_ACTION_TYPES = {"send_message", "post_to_channel"}

    def __init__(self, bot_token: Optional[str] = None) -> None:
        resolved = bot_token or os.environ.get("SLACK_BOT_TOKEN", "")
        if not resolved:
            raise ValueError(
                "SLACK_BOT_TOKEN is required. Set the environment variable or pass "
                "bot_token= to SlackAdapter()."
            )
        self._bot_token = resolved

    # ------------------------------------------------------------------

    def execute(self, action: Any) -> ExecutionResult:
        action_id: str = action.action_id if hasattr(action, "action_id") else action["action_id"]
        action_type: str = action.action_type if hasattr(action, "action_type") else action["action_type"]
        parameters: dict = action.parameters if hasattr(action, "parameters") else action.get("parameters", {})

        if action_type not in self.SUPPORTED_ACTION_TYPES:
            return ExecutionResult(
                success=False,
                result={},
                error=f"SlackAdapter does not handle action_type={action_type!r}",
            )

        # Both action types map to the same underlying call
        return self._post_message(action_id, parameters)

    # ------------------------------------------------------------------

    def _post_message(self, action_id: str, parameters: dict) -> ExecutionResult:
        channel = parameters.get("channel", "")
        text = parameters.get("text", "")
        blocks: Optional[List[Any]] = parameters.get("blocks")

        if not channel:
            return ExecutionResult(success=False, result={}, error="parameters.channel is required")
        if not text:
            return ExecutionResult(success=False, result={}, error="parameters.text is required")

        body: dict[str, Any] = {"channel": channel, "text": text}
        if blocks:
            body["blocks"] = blocks

        try:
            resp = self._request(body)
        except _SlackHTTPError as exc:
            return ExecutionResult(
                success=False,
                result={},
                error=f"Slack API HTTP {exc.status}: {exc.body}",
            )
        except Exception as exc:
            return ExecutionResult(success=False, result={}, error=str(exc))

        if not resp.get("ok"):
            return ExecutionResult(
                success=False,
                result={},
                error=f"Slack error: {resp.get('error', 'unknown')}",
            )

        return ExecutionResult(
            success=True,
            result={
                "ok": resp["ok"],
                "ts": resp.get("ts"),
                "channel": resp.get("channel"),
                "statis_action_id": action_id,
            },
        )

    # ------------------------------------------------------------------

    def _request(self, body: dict) -> dict:
        data = json.dumps(body).encode()
        req = Request(
            _CHAT_POST_URL,
            data=data,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {self._bot_token}",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise _SlackHTTPError(exc.code, exc.read().decode()) from exc


class _SlackHTTPError(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        self.body = body
