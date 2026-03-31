"""
CrewAI + Statis integration example.

Demonstrates how to use StatisActionTool to govern CrewAI agent actions.
Runs in shadow mode by default — no real credentials required.
"""
import os
from statis import StatisClient, StatisActionTool

# Shadow mode — Statis evaluates and receipts the action but doesn't call HubSpot
client = StatisClient(api_key=os.getenv("STATIS_API_KEY", "demo-key"), base_url="http://localhost:8000")

hubspot_update = StatisActionTool(
    action_type="update_contact",
    description="Update a HubSpot contact's properties",
    statis_client=client,
    target_system="hubspot",
)

# In a real CrewAI agent, you'd pass this in the tools list:
# agent = Agent(role="CRM Agent", tools=[hubspot_update], ...)

# Standalone test:
if __name__ == "__main__":
    result = hubspot_update.run(
        target_entity={"type": "contact", "id": "12345"},
        contact_id="12345",
        email="updated@example.com",
        company="Acme Corp",
    )
    print(result)
