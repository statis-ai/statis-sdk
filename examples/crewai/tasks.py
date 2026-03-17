"""Task definitions for the Coordinated Response Crew.

Sequential flow: Triage -> Sentiment -> CSM -> Sales + Billing
"""
from __future__ import annotations

from crewai import Agent, Task


SCENARIO_CONTEXT = {
    "ticket_text": (
        "URGENT: Our login page has been returning 500 errors for the last "
        "30 minutes. None of our 2,000+ users can access the platform. "
        "This is a production outage affecting all customers. We need "
        "immediate resolution. Ticket ID: T-4521."
    ),
    "customer_email": (
        "Subject: UNACCEPTABLE DOWNTIME\n\n"
        "This is the third outage this quarter. Our entire team has been "
        "blocked for over an hour. We are evaluating alternative vendors "
        "and will not renew our contract if this continues. I've already "
        "escalated this to our VP of Engineering.\n\n"
        "— Jamie Chen, Head of Platform, Acme Corp"
    ),
    "entity_type": "account",
    "entity_id": "acct-42",
}


def create_tasks_with_statis(agents: dict[str, Agent], context: dict | None = None) -> list[Task]:
    """Create tasks where agents USE Statis tools to coordinate."""
    ctx = context or SCENARIO_CONTEXT
    et = ctx["entity_type"]
    eid = ctx["entity_id"]

    triage_task = Task(
        description=(
            f"Analyze this support ticket and publish a support.incident_reported "
            f"event to Statis:\n\n"
            f"Ticket text: \"{ctx['ticket_text']}\"\n\n"
            f"You MUST use the statis_push_event tool with:\n"
            f"  entity_type: {et}\n"
            f"  entity_id: {eid}\n"
            f"  event_type: support.incident_reported\n"
            f"  payload: include incident_id, type, status, severity, and summary\n"
            f"  producer: crewai_triage"
        ),
        expected_output=(
            "Confirmation that a support.incident_reported event was published "
            "to Statis, including the severity classification and incident summary."
        ),
        agent=agents["triage"],
    )

    sentiment_task = Task(
        description=(
            f"Analyze this customer email for emotional tone and publish a "
            f"support.sentiment_updated event to Statis:\n\n"
            f"Email: \"{ctx['customer_email']}\"\n\n"
            f"You MUST use the statis_push_event tool with:\n"
            f"  entity_type: {et}\n"
            f"  entity_id: {eid}\n"
            f"  event_type: support.sentiment_updated\n"
            f"  payload: include label (positive/neutral/negative/angry)\n"
            f"  producer: crewai_sentiment"
        ),
        expected_output=(
            "Confirmation that a support.sentiment_updated event was published "
            "to Statis with the sentiment classification."
        ),
        agent=agents["sentiment"],
    )

    csm_task = Task(
        description=(
            f"Read the current state for {et}/{eid} from Statis using the "
            f"statis_read_state tool. Review the combined picture — incidents, "
            f"sentiment, churn risk — and decide whether to escalate.\n\n"
            f"If escalation is warranted, publish a csm.escalation_requested "
            f"event using statis_push_event with:\n"
            f"  entity_type: {et}\n"
            f"  entity_id: {eid}\n"
            f"  event_type: csm.escalation_requested\n"
            f"  payload: include owner, action, and reason\n"
            f"  producer: crewai_csm"
        ),
        expected_output=(
            "A summary of the current entity state, your assessment, and "
            "confirmation that escalation was published (or explanation of "
            "why it was not needed)."
        ),
        agent=agents["csm"],
        context=[triage_task, sentiment_task],
    )

    sales_task = Task(
        description=(
            f"You were about to send an upsell email to this customer.\n\n"
            f"BEFORE sending anything, read the current state for {et}/{eid} "
            f"from Statis using the statis_read_state tool.\n\n"
            f"Based on the state, decide: should you proceed with the upsell "
            f"email, or pause all outbound? Explain your reasoning based on "
            f"what you see in the golden record."
        ),
        expected_output=(
            "Your decision (proceed or pause outreach) with explicit reasoning "
            "citing the state fields you read from Statis (e.g. churn_risk, "
            "blockers, sentiment)."
        ),
        agent=agents["sales"],
        context=[csm_task],
    )

    billing_task = Task(
        description=(
            f"You have pending dunning retries (failed payment follow-ups) "
            f"for this account.\n\n"
            f"BEFORE executing, read the current state for {et}/{eid} from "
            f"Statis using the statis_read_state tool.\n\n"
            f"Based on the state, decide: should you proceed with dunning "
            f"retries, or suspend them? Note that some fields may be redacted "
            f"due to your role permissions — mention what you can and cannot see."
        ),
        expected_output=(
            "Your decision (proceed or suspend dunning) with reasoning. "
            "Explicitly note any fields that appear redacted or missing "
            "due to your role-based access level."
        ),
        agent=agents["billing"],
        context=[csm_task],
    )

    return [triage_task, sentiment_task, csm_task, sales_task, billing_task]


def create_tasks_without_statis(agents: dict[str, Agent], context: dict | None = None) -> list[Task]:
    """Create tasks where agents have NO Statis tools (the failure scenario)."""
    ctx = context or SCENARIO_CONTEXT

    triage_task = Task(
        description=(
            f"Analyze this support ticket and classify its severity:\n\n"
            f"Ticket text: \"{ctx['ticket_text']}\"\n\n"
            f"Classify the severity and summarize the incident."
        ),
        expected_output="Severity classification and incident summary.",
        agent=agents["triage"],
    )

    sentiment_task = Task(
        description=(
            f"Analyze this customer email for emotional tone:\n\n"
            f"Email: \"{ctx['customer_email']}\"\n\n"
            f"Determine the sentiment."
        ),
        expected_output="Sentiment classification.",
        agent=agents["sentiment"],
    )

    csm_task = Task(
        description=(
            "Assess this account's health and decide whether to escalate. "
            "You don't have access to real-time data from Support or Sentiment "
            "teams. Use your best judgment."
        ),
        expected_output="Your assessment and escalation decision.",
        agent=agents["csm"],
    )

    sales_task = Task(
        description=(
            "You have a scheduled upsell campaign for this customer. "
            "Draft an upsell email offering a premium plan upgrade. "
            "You don't have visibility into any ongoing support issues."
        ),
        expected_output="The draft upsell email you would send to the customer.",
        agent=agents["sales"],
    )

    billing_task = Task(
        description=(
            "You have pending dunning retries for this account's failed payment. "
            "Decide whether to proceed with the automated dunning sequence. "
            "You don't have visibility into any ongoing support issues."
        ),
        expected_output="Your decision on whether to proceed with dunning retries.",
        agent=agents["billing"],
    )

    return [triage_task, sentiment_task, csm_task, sales_task, billing_task]
