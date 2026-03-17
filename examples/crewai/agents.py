"""Agent definitions for the Coordinated Response Crew.

Five specialized agents, each with their own Statis API key for identity,
RBAC, and audit trail.
"""
from __future__ import annotations

from crewai import Agent

from statis_tools import (
    make_push_tool,
    make_read_tool,
    make_history_tool,
)


def create_agents(manifest: dict, entity_type: str, entity_id: str) -> dict[str, Agent]:
    """Create all five agents with per-agent Statis tools.

    Args:
        manifest: Key manifest from provision.py
        entity_type: Target entity type (e.g. "account")
        entity_id: Target entity ID (e.g. "acct-42")

    Returns:
        dict mapping agent name to Agent instance
    """
    base_url = manifest.get("base_url", "http://localhost:8000")

    def _key(agent_id: str) -> str:
        return manifest["agent_keys"][agent_id]["raw_key"]

    # ── Triage Agent ─────────────────────────────────────────────────
    triage = Agent(
        role="Support Triage Specialist",
        goal=(
            f"Analyze the incoming support ticket, classify its severity, "
            f"and publish a support.incident_reported event to Statis for "
            f"entity {entity_type}/{entity_id}."
        ),
        backstory=(
            "You are a senior support engineer who processes incoming support "
            "tickets. You classify severity (low, medium, high, critical), "
            "identify the incident type (outage, bug, performance, security), "
            "and publish your findings as a structured event so the rest of "
            "the organization has immediate visibility."
        ),
        tools=[
            make_push_tool(_key("crewai_triage"), base_url),
        ],
        verbose=True,
    )

    # ── Sentiment Agent ──────────────────────────────────────────────
    sentiment = Agent(
        role="Customer Sentiment Analyst",
        goal=(
            f"Analyze the customer's communication for emotional tone and "
            f"publish a support.sentiment_updated event to Statis for "
            f"entity {entity_type}/{entity_id}."
        ),
        backstory=(
            "You are a sentiment analysis specialist. You read customer "
            "communications — emails, chat messages, social media posts — "
            "and determine the emotional tone: positive, neutral, negative, "
            "or angry. You publish your analysis as a structured event."
        ),
        tools=[
            make_push_tool(_key("crewai_sentiment"), base_url),
        ],
        verbose=True,
    )

    # ── CSM Agent ────────────────────────────────────────────────────
    csm = Agent(
        role="Customer Success Manager",
        goal=(
            f"Read the current state for {entity_type}/{entity_id} from Statis, "
            f"assess the combined picture, and if the situation warrants it, "
            f"publish a csm.escalation_requested event."
        ),
        backstory=(
            "You are a Customer Success Manager responsible for account health. "
            "You read the current golden record — which combines incident data, "
            "sentiment, and billing info — and decide whether to escalate. "
            "You always read the shared state before acting, never assume."
        ),
        tools=[
            make_read_tool(_key("crewai_csm"), base_url),
            make_push_tool(_key("crewai_csm"), base_url),
        ],
        verbose=True,
    )

    # ── Sales Agent ──────────────────────────────────────────────────
    sales = Agent(
        role="Sales Account Executive",
        goal=(
            f"Read the current state for {entity_type}/{entity_id} from Statis "
            f"and decide whether to proceed with or pause outbound sales outreach."
        ),
        backstory=(
            "You are a Sales Account Executive. Before sending any outreach "
            "(upsell emails, meeting requests, renewal offers), you ALWAYS "
            "check the current account state in Statis. If there are active "
            "incidents, negative sentiment, or churn risk, you pause all "
            "outbound activity. You never want to email an angry customer "
            "about an upgrade while their system is down."
        ),
        tools=[
            make_read_tool(_key("crewai_sales"), base_url),
        ],
        verbose=True,
    )

    # ── Billing Agent ────────────────────────────────────────────────
    billing = Agent(
        role="Billing Operations Specialist",
        goal=(
            f"Read the current state for {entity_type}/{entity_id} from Statis "
            f"and decide whether to proceed with or suspend dunning retries."
        ),
        backstory=(
            "You are a Billing Operations Specialist. Before executing dunning "
            "retries (failed payment follow-ups), you check the account state "
            "in Statis. If there are active blockers or incidents, you suspend "
            "dunning to avoid antagonizing the customer. Note: due to your role "
            "permissions, some sensitive fields like sentiment may be redacted."
        ),
        tools=[
            make_read_tool(_key("crewai_billing"), base_url),
        ],
        verbose=True,
    )

    return {
        "triage": triage,
        "sentiment": sentiment,
        "csm": csm,
        "sales": sales,
        "billing": billing,
    }


def create_agents_without_statis() -> dict[str, Agent]:
    """Create the same agents but with NO Statis tools (the 'failure' version)."""

    triage = Agent(
        role="Support Triage Specialist",
        goal="Classify the incoming support ticket by severity and type.",
        backstory=(
            "You are a support engineer who processes tickets. You classify "
            "severity and incident type. You have no way to share your findings "
            "with other teams."
        ),
        verbose=True,
    )

    sentiment = Agent(
        role="Customer Sentiment Analyst",
        goal="Analyze the customer's communication for emotional tone.",
        backstory=(
            "You analyze customer communications for sentiment. You determine "
            "the emotional tone but have no way to share this with other teams."
        ),
        verbose=True,
    )

    csm = Agent(
        role="Customer Success Manager",
        goal="Assess the account health and decide whether to escalate.",
        backstory=(
            "You are a CSM responsible for account health. You don't have "
            "access to real-time support or sentiment data from other teams. "
            "You rely on your own assumptions about the account."
        ),
        verbose=True,
    )

    sales = Agent(
        role="Sales Account Executive",
        goal="Decide what outreach to send to the customer today.",
        backstory=(
            "You are a Sales exec. You have a scheduled upsell campaign to send "
            "today. You have no visibility into support incidents or customer "
            "sentiment. You proceed with your normal sales playbook."
        ),
        verbose=True,
    )

    billing = Agent(
        role="Billing Operations Specialist",
        goal="Decide whether to proceed with dunning retries for failed payments.",
        backstory=(
            "You are a Billing specialist. You have pending dunning retries "
            "for this account. You have no visibility into support incidents "
            "or customer sentiment. You follow standard billing procedures."
        ),
        verbose=True,
    )

    return {
        "triage": triage,
        "sentiment": sentiment,
        "csm": csm,
        "sales": sales,
        "billing": billing,
    }
