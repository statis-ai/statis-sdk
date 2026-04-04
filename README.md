# Statis SDK

Python and TypeScript SDKs for [Statis](https://statis.dev) — agent execution infrastructure.

Statis is the governance layer between AI agents and production systems. Every agent action goes through four primitives: **propose → evaluate → execute once → receipt**. The SDKs give you a thin, typed client to interact with the Statis API from your agent code.

## Install

**Python**
```bash
pip install statis-ai
```

**TypeScript / JavaScript**
```bash
npm install statis-ai
```

## Quickstart

### Python

```python
from statis import StatisClient, ActionDeniedError, ActionEscalatedError

with StatisClient(api_key="st_...") as client:
    try:
        receipt = client.execute(
            action_type="retention_offer",
            target={"entity_type": "account", "entity_id": "acct-42"},
            parameters={"discount_pct": 20},
            agent_id="csm-agent-v2",
            target_system="stripe",
        )
        print(f"Approved — receipt: {receipt.receipt_id}, hash: {receipt.hash}")
    except ActionDeniedError as e:
        print(f"Denied by policy: {e}")
    except ActionEscalatedError as e:
        print(f"Escalated for human review: {e.action_id}")
```

### TypeScript

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
console.log(`Approved — receipt: ${receipt.receipt_id}`);
```

## Dry-run / Simulation

Test what a policy would decide before proposing a real action. No DB writes, no receipt.

### Python

```python
from statis import StatisClient

with StatisClient(api_key="st_...") as client:
    result = client.simulate(
        action_type="retention_offer",
        entity_state={"churn_risk": True, "ltv": 1500},
        parameters={"discount_pct": 20},
    )
    print(result.decision)   # APPROVED | DENIED | ESCALATED
    print(result.reason)
    print(result.rule_id)
```

### TypeScript

```typescript
const result = await client.simulate({
  action_type: "retention_offer",
  entity_state: { churn_risk: true, ltv: 1500 },
  parameters: { discount_pct: 20 },
});
console.log(result.decision); // APPROVED | DENIED | ESCALATED
```

## Policy-as-Code CLI

Manage policy rules from YAML files — version them in git, diff before applying.

```bash
pip install statis-ai

export STATIS_API_KEY=st_...
export STATIS_BASE_URL=https://api.statis.dev

# Preview what would change
statis diff policies.yaml

# Apply rules
statis apply policies.yaml

# Simulate a decision from the CLI
statis simulate --action-type retention_offer --entity-state entity.json
```

**policies.yaml format:**

```yaml
version: 1
rules:
  - rule_id: retention_offer_high_value_v1
    action_type: retention_offer
    conditions:
      churn_risk: true
      min_ltv: 1000
    decision: APPROVED
    priority: 100
    active: true
```

## Repo Structure

```
statis-sdk/
├── python/          Python SDK (statis-ai on PyPI)
├── typescript/      TypeScript SDK (statis-ai on npm)
├── adapters/        Production system adapters (Airflow, Salesforce, HubSpot, Zendesk, Slack, GitHub, Linear)
└── examples/        End-to-end demos
```

## Adapters

Adapters execute approved actions against external systems. They follow a simple contract: `execute(action) -> ExecutionResult`.

| Adapter | target_system | Action types |
|---|---|---|
| `GitHubAdapter` | `github` | `github_merge_pr`, `github_create_release`, `github_trigger_workflow`, `github_close_issue` |
| `LinearAdapter` | `linear` | `linear_create_issue`, `linear_update_issue` |
| `SlackAdapter` | `slack` | `slack_send_message`, `slack_update_message` |
| `AirflowAdapter` | `airflow` | `airflow_dag_trigger` |
| `SalesforceAdapter` | `salesforce` | `salesforce_update_record`, `salesforce_create_record` |
| `ZendeskAdapter` | `zendesk` | `zendesk_create_ticket`, `zendesk_update_ticket` |
| `HubSpotAdapter` | `hubspot` | `hubspot_update_contact`, `hubspot_create_deal` |

### Build your own adapter

```python
from adapters.python.base import BaseAdapter, ExecutionResult

class MyAdapter(BaseAdapter):
    def execute(self, action) -> ExecutionResult:
        # action.action_id  — use as idempotency key downstream
        # action.action_type
        # action.parameters — what the agent proposed
        try:
            result = my_system.call(action.parameters, idempotency_key=action.action_id)
            return ExecutionResult(success=True, result=result)
        except Exception as e:
            return ExecutionResult(success=False, error=str(e))
```

## Configuration

| Option | Python | TypeScript | Default |
|---|---|---|---|
| API key | `StatisClient(api_key=...)` or `STATIS_API_KEY` env | `{ api_key: ... }` or `STATIS_API_KEY` env | required |
| Base URL | `StatisClient(base_url=...)` or `STATIS_BASE_URL` env | `{ base_url: ... }` or `STATIS_BASE_URL` env | `https://api.statis.dev` |
| Timeout | `StatisClient(timeout=30)` | `{ timeout: 30000 }` | 30s |

## Links

- [Docs](https://docs.statis.dev)
- [Console](https://console.statis.dev)
- [API Reference](https://docs.statis.dev/api-reference)
- [PyPI](https://pypi.org/project/statis-ai/)
- [npm](https://www.npmjs.com/package/statis-ai)

## License

Apache 2.0 — see [LICENSE](./LICENSE).
