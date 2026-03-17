# CrewAI + Statis Demos

Prove that Statis solves **Agent Amnesia** for stateless CrewAI agents.

## Prerequisites

- Python 3.10+
- Statis API running locally (`cd api && fastapi run app/main.py`)
- PostgreSQL with migrations applied (`cd api && alembic upgrade head`)

## Setup

```bash
cd examples/crewai
pip install -r requirements.txt
```

Set your LLM API key (OpenAI or Anthropic):
```bash
export OPENAI_API_KEY="sk-..."
# or
export ANTHROPIC_API_KEY="sk-ant-..."
```

## Provisioning

All demos auto-provision on first run. Keys are cached in `.statis_demo_keys.json`.

```bash
# Manual provisioning (optional)
python provision.py

# Force fresh tenant
python provision.py --reprovision
```

## Demo 2: Coordinated Response Crew (Primary)

Five agents handle a customer crisis. Before/after contrast.

```bash
# Phase 1: The failure (no shared state)
python demo_without_statis.py

# Phase 2+3: The solution (Statis-coordinated)
python demo_with_statis.py
```

**What to watch for:**
- Without Statis: Sales sends an upsell mid-crisis ❌
- With Statis: Sales reads `churn_risk=true` and pauses ✅
- RBAC: Billing sees `sentiment: [REDACTED]`
- Deterministic `state_hash` across runs

## Demo 1: The Memory Bridge (Tutorial)

Three independent crew runs, one shared golden record.

```bash
python demo_memory_bridge.py
```

**What to watch for:** The evening CSM sees the entire day's context even though each crew run was independent.

## Demo 4: Shadow Audit (Governance)

Junior crew processes events; Senior auditor reviews via time-travel.

```bash
python demo_shadow_audit.py
```

**What to watch for:** The auditor walks through each revision, comparing event payloads to materialized state.

## Demo 3: Multi-Crew Pipeline (Enterprise)

Three independent teams connected via Statis webhooks.

```bash
# Terminal 1: Webhook receiver
python webhook_crew_trigger.py

# Terminal 2: Statis delivery worker
cd ../../worker && python main.py

# Terminal 3: Run the demo
python demo_multi_crew.py
```

**What to watch for:** Support crew publishes events → Statis webhooks trigger Account and Revenue crews automatically.

## Console UI

Open the Statis Console side-by-side to watch events appear in real-time:

```bash
cd ../../console && npm run dev
```

Set `NEXT_PUBLIC_API_KEY` to the master key from `.statis_demo_keys.json` to see full state (no RBAC redaction).

## File Structure

```
provision.py              # Provision-once-cache (signup + per-agent keys)
statis_tools.py           # 4 BaseTool subclasses (Push, Read, History, TimeTravel)
agents.py                 # 5 agent definitions
tasks.py                  # Task definitions (with and without Statis)
crew.py                   # Sequential crew builder
demo_without_statis.py    # Demo 2: failure run
demo_with_statis.py       # Demo 2: success run + RBAC + audit
demo_memory_bridge.py     # Demo 1: 3 crew runs, continuity
demo_shadow_audit.py      # Demo 4: junior + senior audit
demo_multi_crew.py        # Demo 3: 3 independent crews
webhook_crew_trigger.py   # Demo 3: webhook → crew spawner
```
