# statis-sdk

Python and TypeScript SDKs for [Statis](https://statis.dev) — agent execution infrastructure.

## What is Statis?

The layer between your AI agents and production systems. Every agent action goes through four primitives: propose → evaluate → execute once → receipt.

## Install

**Python**
```bash
pip install statis-ai
```

**TypeScript**
```bash
npm install statis-ai
```

## Quickstart

**Python**
```python
from statis import StatisClient, ActionDeniedError, ActionEscalatedError

with StatisClient(api_key="st_...") as client:
    receipt = client.execute(
        action_type="retention_offer",
        target={"entity_type": "account", "entity_id": "acct-42"},
        parameters={"discount_pct": 20},
        agent_id="csm-agent-v2",
        target_system="stripe",
    )
    print(f"Executed — receipt: {receipt.receipt_id}, hash: {receipt.hash}")
```

**TypeScript**
```typescript
import { StatisClient } from "statis-ai";

const client = new StatisClient({ api_key: "st_..." });

const receipt = await client.execute({
  action_type: "retention_offer",
  target: { entity_type: "account", entity_id: "acct-42" },
  parameters: { discount_pct: 20 },
  agent_id: "csm-agent-v2",
  target_system: "stripe",
});
console.log(`Executed — receipt: ${receipt.receipt_id}, hash: ${receipt.hash}`);
```

## Repo Structure

```
statis-sdk/
├── python/          — Python SDK (statis-ai on PyPI)
├── typescript/      — TypeScript SDK (statis-ai on npm)
├── adapters/        — Production system adapters
│   └── python/      — Airflow, Salesforce, HubSpot, Zendesk, Stripe mock
└── examples/        — End-to-end demos
```

## Adapters

| Adapter | target_system | Handles |
|---|---|---|
| `AirflowAdapter` | `airflow` | `airflow_dag_trigger` |
| `SalesforceAdapter` | `salesforce` | `salesforce_update_record`, `salesforce_create_record` |
| `ZendeskAdapter` | `zendesk` | `zendesk_create_ticket`, `zendesk_update_ticket` |
| `HubSpotAdapter` | `hubspot` | `hubspot_update_contact`, `hubspot_create_deal` |
| `MockStripeAdapter` | `stripe` | `retention_offer`, `apply_discount` |

### Add your own adapter

```python
from adapters.python.base import BaseAdapter, ExecutionResult

class MyAdapter(BaseAdapter):
    def execute(self, action) -> ExecutionResult:
        # action.action_id  — use as idempotency key
        # action.parameters — what the agent proposed
        return ExecutionResult(success=True, result={"id": "..."})
```

## Examples

```bash
STATIS_API_KEY=st_... python examples/retention_demo.py
```

## Links

- [Docs](https://docs.statis.dev)
- [Console](https://console.statis.dev)
- [API Reference](https://docs.statis.dev/api-reference)
- [statis-core](https://github.com/statis-ai/statis-core) (private — API, worker, console)

## License

MIT
