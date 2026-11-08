// @vitest-environment jsdom
// Approving a queue item that came from a live agent run must also SUBMIT the sandbox note: the approval is the worker's one click, and the agent's finalize route presses
// the real submit button. Before this, the item showed "approved" while the note stayed a draft. These tests pin what `setQueue` reports in each case.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, forgetBackoff } from "./api";

const item = (over: Record<string, unknown> = {}) => ({ id: "q1", run_id: "run_1", status: "approved", kind: "irreversible_step", ...over });
type Call = { url: string; method: string };
let calls: Call[];

function stubFetch(finalize: { status: number; body?: unknown } | "down", approve: { status: number; body?: unknown } = { status: 200, body: item() }) {
  calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url: String(url), method: String(init?.method ?? "GET") });
    const isFinalize = String(url).includes("/finalize");
    const r = isFinalize ? finalize : approve;
    if (r === "down") throw new TypeError("connection refused");
    return new Response(JSON.stringify(r.body ?? {}), { status: r.status, headers: { "Content-Type": "application/json" } });
  }));
}

beforeEach(() => { forgetBackoff(); });
afterEach(() => { vi.unstubAllGlobals(); });

describe("setQueue: approving submits the note", () => {
  it("approves, then presses submit through the agent, and says it was submitted", async () => {
    stubFetch({ status: 200, body: { submitted: true, reason: "approved by the worker" } });
    const r = await api.setQueue("q1", "approve");
    expect(r.finalize).toBe("submitted");
    expect(calls.map((c) => `${c.method} ${c.url}`)).toEqual(["POST /engine/queue/q1/approve", "POST /agent/run/run_1/finalize"]);
  });

  it("says 'failed' when the agent answers but the submit did not finish, so the screen can say so instead of 'done'", async () => {
    stubFetch({ status: 500, body: { error: { code: "boom", message: "x" } } });
    expect((await api.setQueue("q1", "approve")).finalize).toBe("failed");
    stubFetch({ status: 200, body: { submitted: false, reason: "the note changed" } });
    expect((await api.setQueue("q1", "approve")).finalize).toBe("failed");
  });

  it("treats 409 (no live note: a seeded item or a cached run) and 404 as 'none', quietly", async () => {
    stubFetch({ status: 409, body: { error: { code: "conflict", message: "no note" } } });
    expect((await api.setQueue("q1", "approve")).finalize).toBe("none");
    forgetBackoff();
    stubFetch({ status: 404, body: {} });
    expect((await api.setQueue("q1", "approve")).finalize).toBe("none");
  });

  it("treats an agent that is not running as 'none': the approval stands and there is nothing to submit", async () => {
    stubFetch("down");
    expect((await api.setQueue("q1", "approve")).finalize).toBe("none");
  });

  it("never finalizes a rejection or an item with no run", async () => {
    stubFetch({ status: 200, body: { submitted: true } }, { status: 200, body: item({ status: "rejected" }) });
    expect((await api.setQueue("q1", "reject")).finalize).toBe("none");
    expect(calls.some((c) => c.url.includes("/finalize"))).toBe(false);
    stubFetch({ status: 200, body: { submitted: true } }, { status: 200, body: item({ run_id: "" }) });
    expect((await api.setQueue("q1", "approve")).finalize).toBe("none");
    expect(calls.some((c) => c.url.includes("/finalize"))).toBe(false);
  });

  it("does not finalize when the engine itself refused the approval", async () => {
    stubFetch({ status: 200, body: { submitted: true } }, { status: 403, body: { error: { code: "step_up_required", message: "sign in again" } } });
    await expect(api.setQueue("q1", "approve")).rejects.toThrow();
    expect(calls.some((c) => c.url.includes("/finalize"))).toBe(false);
  });
});
