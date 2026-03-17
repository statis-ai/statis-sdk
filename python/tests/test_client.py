"""Unit tests for StatisClient using respx to mock httpx."""
import pytest
import respx
from httpx import Response

from statis import ActionDeniedError, ActionEscalatedError, ActionTimeoutError, StatisClient, StatisError

BASE = "https://api.statis.dev"

RECEIPT_PAYLOAD = {
    "receipt_id": "rcpt-1",
    "action_id": "act-1",
    "decision": "APPROVED",
    "rule_id": "churn_retention_v1",
    "rule_version": "1",
    "approved_by": "policy_engine",
    "conditions_evaluated": {"churn_risk": {"label": "Churn Risk", "passed": True}},
    "execution_result": {"status": "ok"},
    "executed_at": "2024-01-01T00:00:01+00:00",
    "hash": "abc123",
    "created_at": "2024-01-01T00:00:00+00:00",
}

ACTION_PROPOSED = {
    "action_id": "act-1",
    "status": "PROPOSED",
    "proposed_by": "agent-x",
    "action_type": "retention_offer",
    "target_entity": {"entity_type": "account", "entity_id": "acct-1"},
    "target_system": "stripe",
    "parameters": {},
    "context": {},
    "created_at": "2024-01-01T00:00:00+00:00",
    "updated_at": "2024-01-01T00:00:00+00:00",
}


# ---------------------------------------------------------------------------
# propose()
# ---------------------------------------------------------------------------


@respx.mock
def test_propose_returns_action_id():
    respx.post(f"{BASE}/actions").mock(return_value=Response(201, json=ACTION_PROPOSED))

    with StatisClient(api_key="test-key") as client:
        aid = client.propose(
            action_type="retention_offer",
            target={"entity_type": "account", "entity_id": "acct-1"},
            parameters={},
            agent_id="agent-x",
            target_system="stripe",
            action_id="act-1",
        )

    assert aid == "act-1"


@respx.mock
def test_propose_uses_provided_action_id():
    respx.post(f"{BASE}/actions").mock(return_value=Response(201, json=ACTION_PROPOSED))

    with StatisClient(api_key="k") as client:
        aid = client.propose(
            action_type="retention_offer",
            target={"entity_type": "account", "entity_id": "acct-1"},
            parameters={},
            agent_id="agent-x",
            target_system="stripe",
            action_id="act-1",
        )

    assert aid == "act-1"
    sent = respx.calls[0].request
    import json
    body = json.loads(sent.content)
    assert body["action_id"] == "act-1"
    assert body["proposed_by"] == "agent-x"


@respx.mock
def test_propose_auto_generates_action_id():
    def _echo(req):
        import json
        body = json.loads(req.content)
        return Response(201, json={**ACTION_PROPOSED, "action_id": body["action_id"]})

    respx.post(f"{BASE}/actions").mock(side_effect=_echo)

    with StatisClient(api_key="k") as client:
        aid = client.propose(
            action_type="retention_offer",
            target={"entity_type": "account", "entity_id": "acct-1"},
            parameters={},
            agent_id="agent-x",
            target_system="stripe",
        )

    assert aid.startswith("statis-")


@respx.mock
def test_propose_raises_statis_error_on_4xx():
    respx.post(f"{BASE}/actions").mock(
        return_value=Response(409, json={"detail": "already exists"})
    )

    with StatisClient(api_key="k") as client:
        with pytest.raises(StatisError) as exc_info:
            client.propose(
                action_type="retention_offer",
                target={"entity_type": "account", "entity_id": "acct-1"},
                parameters={},
                agent_id="agent-x",
                target_system="stripe",
                action_id="act-1",
            )

    assert exc_info.value.status_code == 409
    assert "already exists" in exc_info.value.message


# ---------------------------------------------------------------------------
# get_receipt()
# ---------------------------------------------------------------------------


@respx.mock
def test_get_receipt_parses_all_fields():
    respx.get(f"{BASE}/receipts/act-1").mock(
        return_value=Response(200, json=RECEIPT_PAYLOAD)
    )

    with StatisClient(api_key="k") as client:
        r = client.get_receipt("act-1")

    assert r.receipt_id == "rcpt-1"
    assert r.decision == "APPROVED"
    assert r.rule_id == "churn_retention_v1"
    assert r.conditions_evaluated is not None
    assert r.conditions_evaluated["churn_risk"]["passed"] is True
    assert r.execution_result == {"status": "ok"}
    assert r.executed_at is not None
    assert r.hash == "abc123"


@respx.mock
def test_get_receipt_handles_null_optional_fields():
    payload = {**RECEIPT_PAYLOAD, "rule_id": None, "rule_version": None,
               "conditions_evaluated": None, "execution_result": None,
               "executed_at": None}
    respx.get(f"{BASE}/receipts/act-1").mock(return_value=Response(200, json=payload))

    with StatisClient(api_key="k") as client:
        r = client.get_receipt("act-1")

    assert r.rule_id is None
    assert r.conditions_evaluated is None
    assert r.executed_at is None


# ---------------------------------------------------------------------------
# execute() — happy path
# ---------------------------------------------------------------------------


@respx.mock
def test_execute_returns_receipt_on_completed():
    respx.post(f"{BASE}/actions").mock(return_value=Response(201, json=ACTION_PROPOSED))
    respx.post(f"{BASE}/actions/act-1/evaluate").mock(return_value=Response(200, json={}))
    # First poll → EXECUTING, second → COMPLETED
    respx.get(f"{BASE}/actions/act-1").mock(
        side_effect=[
            Response(200, json={**ACTION_PROPOSED, "status": "EXECUTING"}),
            Response(200, json={**ACTION_PROPOSED, "status": "COMPLETED"}),
        ]
    )
    respx.get(f"{BASE}/receipts/act-1").mock(return_value=Response(200, json=RECEIPT_PAYLOAD))

    with StatisClient(api_key="k", poll_interval=0) as client:
        receipt = client.execute(
            action_type="retention_offer",
            target={"entity_type": "account", "entity_id": "acct-1"},
            parameters={},
            agent_id="agent-x",
            target_system="stripe",
            action_id="act-1",
        )

    assert receipt.decision == "APPROVED"


# ---------------------------------------------------------------------------
# execute() — denied
# ---------------------------------------------------------------------------


@respx.mock
def test_execute_raises_action_denied_error():
    respx.post(f"{BASE}/actions").mock(return_value=Response(201, json=ACTION_PROPOSED))
    respx.post(f"{BASE}/actions/act-1/evaluate").mock(return_value=Response(200, json={}))
    respx.get(f"{BASE}/actions/act-1").mock(
        return_value=Response(200, json={**ACTION_PROPOSED, "status": "DENIED"})
    )
    denied_payload = {**RECEIPT_PAYLOAD, "decision": "DENIED"}
    respx.get(f"{BASE}/receipts/act-1").mock(return_value=Response(200, json=denied_payload))

    with StatisClient(api_key="k", poll_interval=0) as client:
        with pytest.raises(ActionDeniedError) as exc_info:
            client.execute(
                action_type="retention_offer",
                target={"entity_type": "account", "entity_id": "acct-1"},
                parameters={},
                agent_id="agent-x",
                target_system="stripe",
                action_id="act-1",
            )

    err = exc_info.value
    assert err.receipt.decision == "DENIED"
    assert err.receipt.action_id == "act-1"


# ---------------------------------------------------------------------------
# execute() — timeout
# ---------------------------------------------------------------------------


@respx.mock
def test_execute_raises_action_timeout_error(monkeypatch):
    respx.post(f"{BASE}/actions").mock(return_value=Response(201, json=ACTION_PROPOSED))
    respx.post(f"{BASE}/actions/act-1/evaluate").mock(return_value=Response(200, json={}))
    # Always return EXECUTING
    respx.get(f"{BASE}/actions/act-1").mock(
        return_value=Response(200, json={**ACTION_PROPOSED, "status": "EXECUTING"})
    )

    # Make time.monotonic() advance past deadline on the first poll check
    import statis.client as _mod
    _calls = [0]

    original = __import__("time").monotonic

    def _fake_monotonic():
        _calls[0] += 1
        # After 2 calls (setup + first poll check), return a large value
        return original() + (_calls[0] * 100)

    monkeypatch.setattr("statis.client.time.monotonic", _fake_monotonic)
    monkeypatch.setattr("statis.client.time.sleep", lambda _: None)

    with StatisClient(api_key="k", poll_interval=0) as client:
        with pytest.raises(ActionTimeoutError) as exc_info:
            client.execute(
                action_type="retention_offer",
                target={"entity_type": "account", "entity_id": "acct-1"},
                parameters={},
                agent_id="agent-x",
                target_system="stripe",
                action_id="act-1",
                timeout=1.0,
            )

    assert exc_info.value.action_id == "act-1"
    assert exc_info.value.timeout == 1.0


# ---------------------------------------------------------------------------
# execute() — escalated
# ---------------------------------------------------------------------------


@respx.mock
def test_execute_raises_action_escalated_error():
    respx.post(f"{BASE}/actions").mock(return_value=Response(201, json=ACTION_PROPOSED))
    respx.post(f"{BASE}/actions/act-1/evaluate").mock(return_value=Response(200, json={}))
    respx.get(f"{BASE}/actions/act-1").mock(
        return_value=Response(200, json={**ACTION_PROPOSED, "status": "ESCALATED"})
    )

    with StatisClient(api_key="k", poll_interval=0) as client:
        with pytest.raises(ActionEscalatedError) as exc_info:
            client.execute(
                action_type="retention_offer",
                target={"entity_type": "account", "entity_id": "acct-1"},
                parameters={},
                agent_id="agent-x",
                target_system="stripe",
                action_id="act-1",
            )

    assert exc_info.value.action_id == "act-1"
    assert "human review" in str(exc_info.value)


# ---------------------------------------------------------------------------
# get_action_status()
# ---------------------------------------------------------------------------


@respx.mock
def test_get_action_status():
    respx.get(f"{BASE}/actions/act-1").mock(
        return_value=Response(200, json={**ACTION_PROPOSED, "status": "ESCALATED"})
    )

    with StatisClient(api_key="k") as client:
        s = client.get_action_status("act-1")

    assert s == "ESCALATED"
