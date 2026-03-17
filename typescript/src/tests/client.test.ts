import { describe, it, mock, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { StatisClient, ActionDeniedError, ActionEscalatedError, ActionTimeoutError, StatisError } from "../index";

const BASE = "https://api.statis.dev";

const RECEIPT_PAYLOAD = {
  receipt_id: "rcpt-1",
  action_id: "act-1",
  decision: "APPROVED",
  rule_id: "churn_retention_v1",
  rule_version: "1",
  approved_by: "policy_engine",
  conditions_evaluated: { churn_risk: { label: "Churn Risk", passed: true } },
  execution_result: { status: "ok" },
  executed_at: "2024-01-01T00:00:01+00:00",
  hash: "abc123",
  created_at: "2024-01-01T00:00:00+00:00",
};

const ACTION_PROPOSED = {
  action_id: "act-1",
  status: "PROPOSED",
  proposed_by: "agent-x",
  action_type: "retention_offer",
  target_entity: { entity_type: "account", entity_id: "acct-1" },
  target_system: "stripe",
  parameters: {},
  context: {},
  created_at: "2024-01-01T00:00:00+00:00",
  updated_at: "2024-01-01T00:00:00+00:00",
};

function makeResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// ---------------------------------------------------------------------------
// propose()
// ---------------------------------------------------------------------------

describe("propose()", () => {
  it("returns action_id from API", async () => {
    const fetchMock = mock.fn(async (_url: string) =>
      makeResponse(201, ACTION_PROPOSED)
    );
    mock.method(globalThis, "fetch", fetchMock);

    const client = new StatisClient({ api_key: "test-key", base_url: BASE });
    const aid = await client.propose({
      action_type: "retention_offer",
      target: { entity_type: "account", entity_id: "acct-1" },
      parameters: {},
      agent_id: "agent-x",
      target_system: "stripe",
      action_id: "act-1",
    });

    assert.equal(aid, "act-1");
    mock.restoreAll();
  });

  it("sends provided action_id and maps agent_id to proposed_by", async () => {
    let capturedBody: Record<string, unknown> = {};
    const fetchMock = mock.fn(async (_url: string, opts: RequestInit) => {
      capturedBody = JSON.parse(opts.body as string);
      return makeResponse(201, ACTION_PROPOSED);
    });
    mock.method(globalThis, "fetch", fetchMock);

    const client = new StatisClient({ api_key: "k", base_url: BASE });
    await client.propose({
      action_type: "retention_offer",
      target: { entity_type: "account", entity_id: "acct-1" },
      parameters: {},
      agent_id: "agent-x",
      target_system: "stripe",
      action_id: "act-1",
    });

    assert.equal(capturedBody["action_id"], "act-1");
    assert.equal(capturedBody["proposed_by"], "agent-x");
    mock.restoreAll();
  });

  it("auto-generates action_id prefixed with statis-", async () => {
    let capturedBody: Record<string, unknown> = {};
    const fetchMock = mock.fn(async (_url: string, opts: RequestInit) => {
      capturedBody = JSON.parse(opts.body as string);
      return makeResponse(201, { ...ACTION_PROPOSED, action_id: capturedBody["action_id"] });
    });
    mock.method(globalThis, "fetch", fetchMock);

    const client = new StatisClient({ api_key: "k", base_url: BASE });
    const aid = await client.propose({
      action_type: "retention_offer",
      target: { entity_type: "account", entity_id: "acct-1" },
      parameters: {},
      agent_id: "agent-x",
      target_system: "stripe",
    });

    assert.ok(aid.startsWith("statis-"));
    mock.restoreAll();
  });

  it("throws StatisError on 4xx", async () => {
    const fetchMock = mock.fn(async () =>
      makeResponse(409, { detail: "already exists" })
    );
    mock.method(globalThis, "fetch", fetchMock);

    const client = new StatisClient({ api_key: "k", base_url: BASE });
    await assert.rejects(
      () =>
        client.propose({
          action_type: "retention_offer",
          target: { entity_type: "account", entity_id: "acct-1" },
          parameters: {},
          agent_id: "agent-x",
          target_system: "stripe",
          action_id: "act-1",
        }),
      (err: unknown) => {
        assert.ok(err instanceof StatisError);
        assert.equal(err.status_code, 409);
        assert.ok(err.message.includes("already exists"));
        return true;
      }
    );
    mock.restoreAll();
  });
});

// ---------------------------------------------------------------------------
// getReceipt()
// ---------------------------------------------------------------------------

describe("getReceipt()", () => {
  it("parses all fields correctly", async () => {
    const fetchMock = mock.fn(async () => makeResponse(200, RECEIPT_PAYLOAD));
    mock.method(globalThis, "fetch", fetchMock);

    const client = new StatisClient({ api_key: "k", base_url: BASE });
    const r = await client.getReceipt("act-1");

    assert.equal(r.receipt_id, "rcpt-1");
    assert.equal(r.decision, "APPROVED");
    assert.equal(r.rule_id, "churn_retention_v1");
    assert.deepEqual(r.conditions_evaluated, { churn_risk: { label: "Churn Risk", passed: true } });
    assert.deepEqual(r.execution_result, { status: "ok" });
    assert.ok(r.executed_at instanceof Date);
    assert.equal(r.hash, "abc123");
    mock.restoreAll();
  });

  it("handles null optional fields", async () => {
    const payload = {
      ...RECEIPT_PAYLOAD,
      rule_id: null,
      rule_version: null,
      conditions_evaluated: null,
      execution_result: null,
      executed_at: null,
    };
    const fetchMock = mock.fn(async () => makeResponse(200, payload));
    mock.method(globalThis, "fetch", fetchMock);

    const client = new StatisClient({ api_key: "k", base_url: BASE });
    const r = await client.getReceipt("act-1");

    assert.equal(r.rule_id, null);
    assert.equal(r.conditions_evaluated, null);
    assert.equal(r.executed_at, null);
    mock.restoreAll();
  });
});

// ---------------------------------------------------------------------------
// execute() — happy path
// ---------------------------------------------------------------------------

describe("execute()", () => {
  it("returns receipt on COMPLETED", async () => {
    let callCount = 0;
    const fetchMock = mock.fn(async (url: string, opts?: RequestInit) => {
      const method = opts?.method ?? "GET";
      if (method === "POST" && (url as string).endsWith("/actions")) {
        return makeResponse(201, ACTION_PROPOSED);
      }
      if (method === "POST" && (url as string).includes("/evaluate")) {
        return makeResponse(200, {});
      }
      if (method === "GET" && (url as string).includes("/actions/act-1")) {
        callCount++;
        const status = callCount === 1 ? "EXECUTING" : "COMPLETED";
        return makeResponse(200, { ...ACTION_PROPOSED, status });
      }
      if (method === "GET" && (url as string).includes("/receipts/act-1")) {
        return makeResponse(200, RECEIPT_PAYLOAD);
      }
      return makeResponse(404, {});
    });
    mock.method(globalThis, "fetch", fetchMock);

    const client = new StatisClient({ api_key: "k", base_url: BASE, poll_interval: 0 });
    const receipt = await client.execute({
      action_type: "retention_offer",
      target: { entity_type: "account", entity_id: "acct-1" },
      parameters: {},
      agent_id: "agent-x",
      target_system: "stripe",
      action_id: "act-1",
    });

    assert.equal(receipt.decision, "APPROVED");
    mock.restoreAll();
  });

  it("throws ActionDeniedError on DENIED", async () => {
    const fetchMock = mock.fn(async (url: string, opts?: RequestInit) => {
      const method = opts?.method ?? "GET";
      if (method === "POST" && (url as string).endsWith("/actions")) return makeResponse(201, ACTION_PROPOSED);
      if (method === "POST") return makeResponse(200, {});
      if ((url as string).includes("/receipts/")) return makeResponse(200, { ...RECEIPT_PAYLOAD, decision: "DENIED" });
      return makeResponse(200, { ...ACTION_PROPOSED, status: "DENIED" });
    });
    mock.method(globalThis, "fetch", fetchMock);

    const client = new StatisClient({ api_key: "k", base_url: BASE, poll_interval: 0 });
    await assert.rejects(
      () =>
        client.execute({
          action_type: "retention_offer",
          target: { entity_type: "account", entity_id: "acct-1" },
          parameters: {},
          agent_id: "agent-x",
          target_system: "stripe",
          action_id: "act-1",
        }),
      (err: unknown) => {
        assert.ok(err instanceof ActionDeniedError);
        assert.equal(err.receipt.decision, "DENIED");
        assert.equal(err.receipt.action_id, "act-1");
        return true;
      }
    );
    mock.restoreAll();
  });

  it("throws ActionEscalatedError on ESCALATED", async () => {
    const fetchMock = mock.fn(async (url: string, opts?: RequestInit) => {
      const method = opts?.method ?? "GET";
      if (method === "POST" && (url as string).endsWith("/actions")) return makeResponse(201, ACTION_PROPOSED);
      if (method === "POST") return makeResponse(200, {});
      return makeResponse(200, { ...ACTION_PROPOSED, status: "ESCALATED" });
    });
    mock.method(globalThis, "fetch", fetchMock);

    const client = new StatisClient({ api_key: "k", base_url: BASE, poll_interval: 0 });
    await assert.rejects(
      () =>
        client.execute({
          action_type: "retention_offer",
          target: { entity_type: "account", entity_id: "acct-1" },
          parameters: {},
          agent_id: "agent-x",
          target_system: "stripe",
          action_id: "act-1",
        }),
      (err: unknown) => {
        assert.ok(err instanceof ActionEscalatedError);
        assert.equal(err.action_id, "act-1");
        assert.ok(err.message.includes("human review"));
        return true;
      }
    );
    mock.restoreAll();
  });

  it("throws ActionTimeoutError when deadline exceeded", async () => {
    const fetchMock = mock.fn(async (url: string, opts?: RequestInit) => {
      const method = opts?.method ?? "GET";
      if (method === "POST" && (url as string).endsWith("/actions")) return makeResponse(201, ACTION_PROPOSED);
      if (method === "POST") return makeResponse(200, {});
      return makeResponse(200, { ...ACTION_PROPOSED, status: "EXECUTING" });
    });
    mock.method(globalThis, "fetch", fetchMock);

    const client = new StatisClient({ api_key: "k", base_url: BASE, poll_interval: 0 });
    await assert.rejects(
      () =>
        client.execute({
          action_type: "retention_offer",
          target: { entity_type: "account", entity_id: "acct-1" },
          parameters: {},
          agent_id: "agent-x",
          target_system: "stripe",
          action_id: "act-1",
          timeout: 0.001, // 1ms — will expire immediately
        }),
      (err: unknown) => {
        assert.ok(err instanceof ActionTimeoutError);
        assert.equal(err.action_id, "act-1");
        return true;
      }
    );
    mock.restoreAll();
  });
});

// ---------------------------------------------------------------------------
// getActionStatus()
// ---------------------------------------------------------------------------

describe("getActionStatus()", () => {
  it("returns raw status string", async () => {
    const fetchMock = mock.fn(async () =>
      makeResponse(200, { ...ACTION_PROPOSED, status: "ESCALATED" })
    );
    mock.method(globalThis, "fetch", fetchMock);

    const client = new StatisClient({ api_key: "k", base_url: BASE });
    const status = await client.getActionStatus("act-1");

    assert.equal(status, "ESCALATED");
    mock.restoreAll();
  });
});
