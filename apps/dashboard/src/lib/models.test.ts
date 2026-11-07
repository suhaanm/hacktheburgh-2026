import { describe, expect, it } from "vitest";
import fx from "../fixtures/models-status.json";
import { directRoles, fmtMs, fmtUsd, healthReading, latencyText, looksLikeKey, normaliseModelsStatus, roleLabel, scalarRows, stripSecrets, totalCalls, totalCost } from "./models";

describe("model status", () => {
  const s = normaliseModelsStatus(fx);
  it("reads the agent service's shape: roles and providers as maps", () => {
    expect(s.roles.map((r) => r.role)).toEqual(["point", "glance", "verify"]);
    expect(s.roles[0].steps.map((x) => x.when)).toEqual(["primary", "escalate", "fallback"]);
    expect(s.providers.map((p) => p.name)).toEqual(["openai", "gemini"]);
    expect(s.providers[1].breaker?.state).toBe("closed");
    expect(s.mock).toBe(true);
    expect(s.config_error).toBeNull();
  });
  it("reads a flat list of roles as well", () => {
    const flat = normaliseModelsStatus({ roles: [{ role: "glance", provider: "gemini", model_id: "m1", fallback: "openai", health: "ok", breaker: "closed", last_latency_ms: 800, calls: 3, cost_usd_est: 0.01 }] });
    expect(flat.roles[0].steps).toEqual([{ provider: "gemini", tier: "", when: "primary", model: "m1" }, { provider: "openai", tier: "", when: "fallback", model: null }]);
  });
  it("tolerates a status with nothing in it", () => {
    const e = normaliseModelsStatus({});
    expect(e.roles).toEqual([]);
    expect(e.meter).toEqual([]);
    expect(totalCost(e.meter)).toBeNull();
    expect(normaliseModelsStatus(null).providers).toEqual([]);
  });
  it("totals cost only over priced calls and says so when there are none", () => {
    expect(totalCost(s.meter)).toBeCloseTo(0.0248, 4);
    expect(totalCalls(s.meter)).toEqual({ n: 38, ok: 37, failed: 1 });
    expect(fmtUsd(null)).toBe("none yet");
    expect(fmtUsd(0)).toBe("$0.00");
    expect(fmtUsd(0.0248)).toBe("$0.025");
    expect(fmtUsd(0.0042)).toBe("$0.0042");
    expect(fmtUsd(3.456)).toBe("$3.46");
    expect(fmtMs(null)).toBe("no calls yet");
    expect(fmtMs(1380)).toBe("1.4 s");
    expect(fmtMs(880)).toBe("880 ms");
  });
  it("reads health in words and lets an open breaker win", () => {
    expect(healthReading({ health: "ok", configured: true, breaker: { state: "closed", recent_failures: 0, retry_in_s: 0, opened_count: 0 } }).label).toBe("Working");
    expect(healthReading({ health: "ok", configured: true, breaker: { state: "open", recent_failures: 5, retry_in_s: 12.2, opened_count: 1 } })).toEqual({ label: "Paused after failures, retrying in 13 s", tone: "bad" });
    expect(healthReading({ health: "unknown", configured: false, breaker: null }).label).toBe("Not set up");
    expect(healthReading({ health: "unknown", configured: true, breaker: null }).label).toBe("Not called yet");
    expect(healthReading({ health: "degraded", configured: true, breaker: null }).tone).toBe("warn");
  });
  it("lists planner, fast and computer-use ids when OpenAI is set up", () => {
    expect(directRoles(s.providers).map((r) => r.role)).toEqual(["planner", "fast", "computer_use"]);
    expect(directRoles([{ name: "openai", configured: false, models: null, breaker: null, health: "unknown" }])).toEqual([]);
  });
  it("names roles plainly", () => {
    expect(roleLabel("glance")).toMatch(/screen state/);
    expect(roleLabel("some_new_role")).toBe("some new role");
  });
});

describe("secrets never reach the page", () => {
  it("drops fields that are called like a key, deeply", () => {
    const out = stripSecrets({ a: 1, api_key: "sk-aaaaaaaaaaaaaaaa", nested: { OPENAI_API_KEY: "x", token: "y", input_tokens: 5, ok: true }, list: [{ secret: "z", name: "fine" }] });
    expect(out).toEqual({ a: 1, nested: { input_tokens: 5, ok: true }, list: [{ name: "fine" }] });
  });
  it("replaces values that look like a key, whatever the field is called", () => {
    expect(stripSecrets({ note: "sk-proj-abcdefghijklmnop" })).toEqual({ note: "[removed]" });
    expect(stripSecrets({ note: "AIzaSyA1234567890abcdefghijklmnopqrstuv" })).toEqual({ note: "[removed]" });
    expect(stripSecrets({ note: "Bearer abcdefghijklmnop1234" })).toEqual({ note: "[removed]" });
    expect(stripSecrets({ note: "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.abcdef" })).toEqual({ note: "[removed]" });
  });
  it("keeps model ids, even long ones", () => {
    for (const id of ["gemini-3.8-flash-lite-preview-extended-thinking", "gemini-2.5-computer-use-preview-10-2025", "fast-model-id", "gpt-5.4-mini"]) expect(looksLikeKey(id)).toBe(false);
    expect(stripSecrets({ model: "gemini-3.8-flash-lite-preview-extended-thinking" })).toEqual({ model: "gemini-3.8-flash-lite-preview-extended-thinking" });
  });
  it("strips them in the normalised status too", () => {
    const n = normaliseModelsStatus({ ...fx, providers: { openai: { configured: true, api_key: "sk-aaaaaaaaaaaaaaaaaaaa", models: { planner: "sk-bbbbbbbbbbbbbbbbbbbbb", fast: "ok-model" }, health: "ok" } } });
    const text = JSON.stringify(n);
    expect(text).not.toMatch(/sk-/);
    expect(text).not.toMatch(/api_key/);
  });
});

describe("table helpers", () => {
  it("makes a table of the scalar columns only", () => {
    const t = scalarRows([{ model: "a", p50_ms: 812.34567, n: 60, deep: { x: 1 }, ok: true }, { model: "b", p50_ms: 900, n: 60, deep: { x: 2 }, ok: false }]);
    expect(t.cols).toEqual(["model", "p50_ms", "n", "ok"]);
    expect(t.rows[0]).toEqual({ model: "a", p50_ms: "812.346", n: "60", ok: "true" });
    expect(scalarRows(undefined)).toEqual({ cols: [], rows: [] });
  });
  it("lists latencies", () => {
    expect(latencyText([880.2, 910])).toBe("880, 910 ms");
    expect(latencyText([])).toBe("none yet");
  });
});
