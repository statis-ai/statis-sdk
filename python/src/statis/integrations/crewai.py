"""CrewAI integration for Statis — duck-typed tool that governs agent actions.

StatisActionTool satisfies the CrewAI BaseTool duck-type interface
(``name``, ``description``, ``run``) without subclassing crewai.BaseTool,
so CrewAI is an optional dependency.

Usage::

    from statis import StatisClient, StatisActionTool

    client = StatisClient(api_key="...", base_url="https://api.statis.dev")

    tool = StatisActionTool(
        action_type="update_contact",
        description="Update a HubSpot contact's properties",
        statis_client=client,
        target_system="hubspot",
    )

    # Pass to CrewAI agent:
    # agent = Agent(role="CRM Agent", tools=[tool], ...)

    # Or call directly:
    result = tool.run(target_entity={"type": "contact", "id": "12345"}, email="new@example.com")
"""
from __future__ import annotations

import uuid
from typing import Any

from .._models import ActionDeniedError, ActionEscalatedError


class StatisActionTool:
    """Governs a single action type for use in CrewAI (or any tool-calling agent).

    Duck-types CrewAI's ``BaseTool`` interface: ``name``, ``description``, ``run``.
    Does not subclass ``crewai.BaseTool`` — CrewAI is not a required dependency.

    Parameters
    ----------
    action_type:
        The Statis action type string (e.g. ``"update_contact"``).
    description:
        Human-readable description of what this tool does. Shown to the LLM.
    statis_client:
        An initialised :class:`statis.StatisClient` instance.
    agent_id:
        Identifier for the calling agent, used for audit trail.
        Defaults to ``"crewai-agent"``.
    target_system:
        The downstream system this action targets (e.g. ``"hubspot"``).
        Defaults to ``"generic"``.
    """

    def __init__(
        self,
        action_type: str,
        description: str,
        statis_client: Any,
        agent_id: str = "crewai-agent",
        target_system: str = "generic",
    ) -> None:
        self.name: str = action_type
        self.description: str = description
        self._client = statis_client
        self._action_type = action_type
        self._agent_id = agent_id
        self._target_system = target_system

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    def run(self, **kwargs: Any) -> str:
        """Propose and execute the action via Statis, returning a status string.

        Keyword arguments are forwarded as ``parameters`` to the Statis API.
        The special key ``target_entity`` (dict) is extracted and passed as
        the ``target`` argument.

        Returns a human-readable result string suitable for LLM consumption.
        """
        action_id = str(uuid.uuid4())
        target_entity: dict[str, Any] = kwargs.pop("target_entity", {})
        parameters: dict[str, Any] = kwargs

        try:
            receipt = self._client.execute(
                action_id=action_id,
                action_type=self._action_type,
                target=target_entity,
                parameters=parameters,
                agent_id=self._agent_id,
                target_system=self._target_system,
            )
            return f"Action {action_id} completed: {receipt.decision}"
        except ActionDeniedError as exc:
            return f"Action denied by policy: {exc}"
        except ActionEscalatedError:
            return f"Action escalated for human review. Action ID: {action_id}"
