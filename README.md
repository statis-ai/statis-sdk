<p align="center">
  <a href="https://statis.dev">
    <img src="https://raw.githubusercontent.com/statis-ai/statis-sdk/main/assets/logo.svg" alt="Statis" width="300" />
  </a>
</p>

<h1 align="center">Statis SDK</h1>

<p align="center">
  <b>The governance layer between AI agents and production systems.</b><br/>
  Every agent action: proposed, evaluated by policy, executed exactly once, and receipted.
</p>

<p align="center">
  <a href="https://statis.dev">statis.dev</a>
  &nbsp;·&nbsp;
  <a href="https://docs.statis.dev">Docs</a>
  &nbsp;·&nbsp;
  <a href="https://console.statis.dev">Console</a>
  &nbsp;·&nbsp;
  <a href="https://x.com/statis_ai">Twitter</a>
</p>

<p align="center">
  <a href="https://github.com/statis-ai/statis-sdk/stargazers"><img src="https://img.shields.io/github/stars/statis-ai/statis-sdk?style=social" alt="GitHub Stars" /></a>
  &nbsp;
  <a href="https://pypi.org/project/statis-ai/"><img src="https://img.shields.io/pypi/v/statis-ai?label=PyPI&color=3B82F6" alt="PyPI" /></a>
  &nbsp;
  <a href="https://www.npmjs.com/package/statis-ai"><img src="https://img.shields.io/npm/v/statis-ai?label=npm&color=CB3837" alt="npm" /></a>
  &nbsp;
  <a href="https://pypi.org/project/statis-ai/"><img src="https://img.shields.io/pypi/dm/statis-ai?label=PyPI%20downloads&color=3B82F6" alt="PyPI Downloads" /></a>
  &nbsp;
  <a href="https://github.com/statis-ai/statis-sdk/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-green" alt="License" /></a>
</p>

---

## The problem

AI agents need to act on the world — merge a PR, apply a discount, trigger a workflow, close a ticket. Right now, those actions are:

- **Invisible** — no paper trail of what was proposed or why
- **Uncontrolled** — no deterministic policy layer between the agent and production
- **Irreversible** — no audit trail, no tamper-evident proof of what ran

Teams slow down agents or keep humans in the loop for everything — not because they distrust AI, but because they have no infrastructure to trust it.

## The solution

Statis is the governance layer that sits between your agents and your production systems. Every action goes through four primitives:

```
Agent proposes action
       │
       ▼
  Policy Engine  ──── APPROVED ────► Execute exactly once ──► Receipt + hash
       │
       ├── DENIED ──► Blocked. Rule logged.
       │
       └── ESCALATED ──► Human review queue (Console)
```

| Primitive | What it does |
|---|---|
| **Action Contract** | Agent proposes before executing. Immutable record from the start. |
| **Policy Engine** | Deterministic rules evaluate the proposal — APPROVED, DENIED, or ESCALATED |
| **Execution Guarantee** | Distributed lock. The action executes exactly once, no matter what. |
| **Receipt** | SHA-256 tamper-evident receipt. Who proposed it, what policy said, what ran. |

---

## Install

```bash
# Python
pip install statis-ai

# TypeScript / JavaScript
npm install statis-ai
```

---

## Quickstart

### Python

```python
from statis import StatisClient, ActionDeniedError, ActionEscalatedError

with StatisClient(api_key="st_...") as client:
    try:
        receipt = client.execute(
            action_type="send_offer",
            target={"entity_type": "account", "entity_id": "acct-42"},
            parameters={"discount_pct": 20, "channel": "email"},
            agent_id="retention-agent-v2",
            target_system="stripe",
        )
        print(f"Done — receipt: {receipt.receipt_id}")
        print(f"Hash: {receipt.hash}")  # SHA-256, tamper-evident

    except ActionDeniedError as e:
        print(f"Blocked by policy rule: {e.receipt.rule_id}")

    except ActionEscalatedError as e:
        print(f"Needs human review — check the Console: {e.action_id}")
```

`execute()` is a single blocking call: propose → evaluate → poll to completion → return receipt. Raises typed exceptions for every terminal state — no stringly-typed status checks.

### TypeScript

```typescript
import { StatisClient, ActionDeniedError, ActionEscalatedError } from "statis-ai";

const client = new StatisClient({ api_key: "st_..." });

try {
  const receipt = await client.execute({
    action_type: "send_offer",
    target: { entity_type: "account", entity_id: "acct-42" },
    parameters: { discount_pct: 20, channel: "email" },
    agent_id: "retention-agent-v2",
    target_system: "stripe",
  });
  console.log(`Done — receipt: ${receipt.receipt_id}, hash: ${receipt.hash}`);

} catch (e) {
  if (e instanceof ActionDeniedError) console.error(`Denied: ${e.receipt?.rule_id}`);
  if (e instanceof ActionEscalatedError) console.error(`Escalated: ${e.action_id}`);
}
```

---

## Test policies before deploying

Simulate a policy decision without proposing a real action. No DB writes. No side effects.

```python
result = client.simulate(
    action_type="send_offer",
    entity_state={"churn_risk": True, "ltv": 1500, "last_discount_days": 45},
    parameters={"discount_pct": 20},
)

print(result.decision)   # APPROVED
print(result.rule_id)    # churn_retention_v1
print(result.reason)     # all conditions passed
```

Use this in your test suite to assert that your policy rules behave as expected before promoting to production.

---

## Policy as Code

Write policies as YAML. Diff before you apply. Version them in git alongside your agent code.

```yaml
# policies.yaml
version: 1
rules:
  - rule_id: send_offer_high_value_v1
    action_type: send_offer
    conditions:
      churn_risk: true
      min_ltv: 1000
      no_discount_days: 30
    decision: APPROVED
    priority: 100
    active: true

  - rule_id: send_offer_deny_default_v1
    action_type: send_offer
    conditions: {}
    decision: DENIED
    priority: 1
    active: true
```

```bash
export STATIS_API_KEY=st_...
export STATIS_BASE_URL=https://api.statis.dev

# Preview what would change — no writes
statis diff policies.yaml

# Apply
statis apply policies.yaml

# Dry-run a decision from the CLI
statis simulate --action-type send_offer --entity-state entity.json
```

---

## Works with every major agent framework

| Framework | Integration |
|---|---|
| **OpenAI Agents SDK** | Wrap any tool call with `client.execute()` |
| **LangChain / LangGraph** | Use as a tool executor node |
| **CrewAI** | Drop into any crew task step |
| **AutoGen / AG2** | Intercept agent actions before execution |
| **LlamaIndex** | Use as a guardrail layer on function calling |
| **Custom agents** | Single `execute()` call — no framework coupling |

---

## Adapters

Adapters execute approved actions against external systems. Every adapter is idempotent — `action_id` is passed as the external system's idempotency key.

| Adapter | target_system | Action types |
|---|---|---|
| `GitHubAdapter` | `github` | `github_merge_pr` · `github_create_release` · `github_trigger_workflow` · `github_close_issue` |
| `LinearAdapter` | `linear` | `linear_create_issue` · `linear_update_issue` |
| `SlackAdapter` | `slack` | `slack_send_message` · `slack_update_message` |
| `AirflowAdapter` | `airflow` | `airflow_dag_trigger` |
| `SalesforceAdapter` | `salesforce` | `salesforce_update_record` · `salesforce_create_record` |
| `ZendeskAdapter` | `zendesk` | `zendesk_create_ticket` · `zendesk_update_ticket` |
| `HubSpotAdapter` | `hubspot` | `hubspot_update_contact` · `hubspot_create_deal` |

### Build your own

```python
from adapters.python.base import BaseAdapter, ExecutionResult

class MyAdapter(BaseAdapter):
    def execute(self, action) -> ExecutionResult:
        # action.action_id  — use as idempotency key downstream
        # action.action_type
        # action.parameters — what the agent proposed
        try:
            result = my_system.call(
                action.parameters,
                idempotency_key=action.action_id,
            )
            return ExecutionResult(success=True, result=result)
        except Exception as e:
            return ExecutionResult(success=False, error=str(e))
```

---

## Configuration

| Option | Python | TypeScript | Default |
|---|---|---|---|
| API key | `StatisClient(api_key=...)` or `STATIS_API_KEY` | `{ api_key: ... }` or `STATIS_API_KEY` | required |
| Base URL | `StatisClient(base_url=...)` or `STATIS_BASE_URL` | `{ base_url: ... }` or `STATIS_BASE_URL` | `https://api.statis.dev` |
| Timeout (s) | `StatisClient(timeout=30)` | `{ timeout: 30000 }` | 30s |

---

## Repo structure

```
statis-sdk/
├── python/       Python SDK (published to PyPI as statis-ai)
├── typescript/   TypeScript SDK (published to npm as statis-ai)
├── adapters/     Adapter implementations (GitHub, Linear, Slack, Airflow, Salesforce, ...)
└── examples/     End-to-end demos
```

---

## Why Statis

| Without Statis | With Statis |
|---|---|
| Agents execute directly — no policy layer | Every action evaluated against deterministic rules before execution |
| No audit trail | Tamper-evident SHA-256 receipt for every action |
| Duplicate execution on retries | Distributed lock — exactly-once guarantee |
| Humans review everything or nothing | Escalation queue — only ambiguous actions need review |
| Policy logic scattered in agent code | Centralized policy rules, versioned as YAML, diffable in PRs |

---

## Links

- [Docs](https://docs.statis.dev) — guides, API reference, SDK reference
- [Console](https://console.statis.dev) — escalation queue, policy builder, audit logs
- [PyPI](https://pypi.org/project/statis-ai/) — Python SDK
- [npm](https://www.npmjs.com/package/statis-ai) — TypeScript SDK
- [statis.dev](https://statis.dev) — website

---

## License

Apache 2.0 — see [LICENSE](./LICENSE).
