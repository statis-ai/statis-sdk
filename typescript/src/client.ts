import { randomUUID } from "crypto";
import {
  ActionDeniedError,
  ActionEscalatedError,
  ActionTimeoutError,
  ExecuteOptions,
  ProposeOptions,
  Receipt,
  StatisError,
} from "./types";

export class StatisClient {
  private readonly baseUrl: string;
  private readonly headers: Record<string, string>;
  private readonly defaultTimeout: number;
  private readonly defaultPollInterval: number;

  constructor(options: {
    api_key?: string;
    base_url?: string;
    timeout?: number;
    poll_interval?: number;
  } = {}) {
    const apiKey = options.api_key ?? process.env["STATIS_API_KEY"] ?? "";
    this.baseUrl = (options.base_url ?? "https://api.statis.dev").replace(/\/$/, "");
    this.headers = {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
    };
    this.defaultTimeout = options.timeout ?? 30;
    this.defaultPollInterval = options.poll_interval ?? 0.5;
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /** Propose an action and return the action_id. */
  async propose(options: ProposeOptions): Promise<string> {
    const body = {
      action_id: options.action_id ?? `statis-${randomUUID()}`,
      action_type: options.action_type,
      target_entity: options.target,
      parameters: options.parameters,
      proposed_by: options.agent_id,
      target_system: options.target_system,
      context: options.context ?? {},
    };
    const data = await this._post("/actions", body);
    return data.action_id as string;
  }

  /**
   * Propose, evaluate, wait for execution, and return the Receipt.
   *
   * @throws {ActionDeniedError} if the policy engine denies the action
   * @throws {ActionEscalatedError} if the action requires human review
   * @throws {ActionTimeoutError} if execution doesn't complete within timeout
   */
  async execute(options: ExecuteOptions): Promise<Receipt> {
    const aid = await this.propose(options);

    await this._post(`/actions/${aid}/evaluate`, undefined);

    const timeout = options.timeout ?? this.defaultTimeout;
    const pollInterval = options.poll_interval ?? this.defaultPollInterval;
    const deadline = Date.now() + timeout * 1000;

    while (true) {
      const data = await this._get(`/actions/${aid}`);
      const status = data.status as string;

      if (status === "DENIED") {
        const receipt = await this.getReceipt(aid);
        throw new ActionDeniedError(receipt);
      }

      if (status === "ESCALATED") {
        throw new ActionEscalatedError(aid);
      }

      if (status === "COMPLETED" || status === "FAILED") {
        return this.getReceipt(aid);
      }

      if (Date.now() >= deadline) {
        throw new ActionTimeoutError(aid, timeout);
      }

      await sleep(pollInterval * 1000);
    }
  }

  /** Return the current status string for an action (e.g. 'ESCALATED', 'COMPLETED'). */
  async getActionStatus(action_id: string): Promise<string> {
    const data = await this._get(`/actions/${action_id}`);
    return data.status as string;
  }

  /** Fetch the receipt for a completed (or denied) action. */
  async getReceipt(action_id: string): Promise<Receipt> {
    const data = await this._get(`/receipts/${action_id}`);
    return parseReceipt(data);
  }

  // ---------------------------------------------------------------------------
  // HTTP helpers
  // ---------------------------------------------------------------------------

  private async _get(path: string): Promise<Record<string, unknown>> {
    const resp = await fetch(`${this.baseUrl}${path}`, { headers: this.headers });
    return this._handleResponse(resp);
  }

  private async _post(
    path: string,
    body: Record<string, unknown> | undefined
  ): Promise<Record<string, unknown>> {
    const resp = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: this.headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    return this._handleResponse(resp);
  }

  private async _handleResponse(resp: Response): Promise<Record<string, unknown>> {
    if (!resp.ok) {
      let message: string;
      try {
        const json = (await resp.json()) as Record<string, unknown>;
        message = (json["detail"] as string) ?? resp.statusText;
      } catch {
        message = resp.statusText;
      }
      throw new StatisError(resp.status, message);
    }
    return resp.json() as Promise<Record<string, unknown>>;
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function parseReceipt(data: Record<string, unknown>): Receipt {
  return {
    receipt_id: data["receipt_id"] as string,
    action_id: data["action_id"] as string,
    decision: data["decision"] as string,
    rule_id: (data["rule_id"] as string | null) ?? null,
    rule_version: (data["rule_version"] as string | null) ?? null,
    approved_by: data["approved_by"] as string,
    conditions_evaluated:
      (data["conditions_evaluated"] as Record<string, unknown> | null) ?? null,
    execution_result:
      (data["execution_result"] as Record<string, unknown> | null) ?? null,
    executed_at: data["executed_at"] ? new Date(data["executed_at"] as string) : null,
    hash: data["hash"] as string,
    created_at: new Date(data["created_at"] as string),
  };
}
