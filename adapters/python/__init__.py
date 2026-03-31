from .base import BaseAdapter, ExecutionResult
from .airflow import AirflowAdapter
from .github_actions import GitHubActionsAdapter
from .hubspot import HubSpotAdapter
from .linear import LinearAdapter
from .mcp_proxy import MCPProxyAdapter
from .salesforce import SalesforceAdapter
from .slack import SlackAdapter
from .stripe_mock import MockStripeAdapter
from .zendesk import ZendeskAdapter

__all__ = [
    "BaseAdapter",
    "ExecutionResult",
    "AirflowAdapter",
    "GitHubActionsAdapter",
    "HubSpotAdapter",
    "LinearAdapter",
    "MCPProxyAdapter",
    "SalesforceAdapter",
    "SlackAdapter",
    "MockStripeAdapter",
    "ZendeskAdapter",
]
