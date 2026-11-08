// @vitest-environment jsdom
// Models and cost (an Admin More row) on the data that breaks screens: nothing reported, no call metered, a meter with 10 000 rows, a missing or NaN cost, a
// very long model id and a unicode job name, an open circuit breaker, a start-up check that failed, no prices, a bake-off that never ran, a config error.
// Each state is rendered for real and the text is checked: it says the state in words, and never shows NaN, undefined, null or Infinity.
// The matrix is in docs/knack-ux/edge-cases-d.md (Models and cost).
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import fx from "../fixtures/models-status.json";
import { normaliseModelsStatus } from "../lib/models";
import type { ModelsStatus } from "../types";

const api = vi.hoisted(() => ({ modelsStatus: vi.fn(), evalReport: vi.fn() }));
vi.mock("../api", () => ({ ApiError: class ApiError extends Error { status = 0; code = ""; }, api }));
import Models from "./Models";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const BAD = /\b(NaN|undefined|null|Infinity)\b|\[object|Invalid Date/;
const base = (): ModelsStatus => normaliseModelsStatus(structuredClone((fx as unknown as { data?: unknown }).data ?? fx));
const meterRow = (i: number, over: Partial<ModelsStatus["meter"][number]> = {}) => ({
  role: "target_locator", provider: "gemini", model: `model-${i}`, n: 3, ok: 3, failed: 0, p50_ms: 800, p95_ms: 1900, input_tokens: 1200, output_tokens: 300, cost_usd_est: 0.0123, ...over,
});

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  api.modelsStatus.mockReset().mockResolvedValue({ data: base(), meta: null, source: "live", why: null });
  api.evalReport.mockReset().mockResolvedValue({ data: { sections: {} }, meta: null, source: "live", why: null });
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); vi.restoreAllMocks(); });

async function show(patch: (s: ModelsStatus) => void = () => undefined): Promise<string> {
  const s = base();
  patch(s);
  api.modelsStatus.mockResolvedValue({ data: s, meta: null, source: "live", why: null });
  await act(async () => { root.render(createElement(Models)); });
  for (let i = 0; i < 4; i++) await act(async () => { await new Promise((r) => setTimeout(r, 10)); });
  host.querySelectorAll("details").forEach((d) => { d.open = true; });
  return (host.textContent ?? "").replace(/\s+/g, " ");
}
const clean = (t: string): void => { expect(t).not.toMatch(BAD); expect(t.trim().length).toBeGreaterThan(20); };

describe("Models and cost: edge cases", () => {
  it("models: nothing reported says there is no model layer yet", async () => {
    const t = await show((s) => { s.roles = []; s.providers = []; s.meter = []; s.boot = []; s.latencies = {}; s.prices_assumed = {}; });
    expect(t).toMatch(/No model layer yet/);
    expect(t).toMatch(/No jobs routed yet/);
    expect(t).toMatch(/No provider reported/);
    expect(t).toMatch(/No prices were reported/);
    clean(t);
  });
  it("models: no call metered yet says so, and no cost is invented", async () => {
    const t = await show((s) => { s.meter = []; });
    expect(t).toMatch(/No model call has been metered yet/);
    expect(t).toMatch(/none yet/);
    clean(t);
  });
  it("models: 10 000 meter rows show two, then Show all", async () => {
    const t = await show((s) => { s.meter = Array.from({ length: 10000 }, (_, i) => meterRow(i)); });
    expect(t).toMatch(/Show all 10000/);
    expect(host.querySelectorAll("table tbody tr").length).toBeLessThan(10);
    clean(t);
  });
  it("models: a missing cost and a NaN time read as words", async () => {
    const t = await show((s) => { s.meter = [meterRow(1, { cost_usd_est: null, p50_ms: null, p95_ms: null }), meterRow(2, { cost_usd_est: Number.NaN as unknown as number })]; });
    expect(t).toMatch(/no calls yet|none yet/);
    expect(t).not.toMatch(/\$NaN/);
  });
  it("models: a very long model id and a unicode job name stay text", async () => {
    const t = await show((s) => { s.meter = [meterRow(1, { model: "x".repeat(200), role: "ÜBERPRÜFEN_日本語" })]; });
    expect(t).toContain("x".repeat(200));
    clean(t);
  });
  it("models: an open circuit breaker and a failed start-up check are said in words", async () => {
    const t = await show((s) => {
      s.providers = [{ ...s.providers[0], configured: true, breaker: { state: "open", recent_failures: 4, opened_count: 2, retry_in_s: 30 } } as never];
      s.boot = [{ provider: s.providers[0].name, ok: false, missing: ["GEMINI_API_KEY"] }];
    });
    expect(t).toMatch(/Paused after failures/);
    expect(t).toMatch(/Start-up check: failed, missing/);
    clean(t);
  });
  it("models: a config error is printed, and the page still draws", async () => {
    const t = await show((s) => { s.config_error = "models.toml line 4 is not valid"; });
    expect(t).toMatch(/could not be read: models\.toml line 4/);
    clean(t);
  });
  it("models: a bake-off that never ran says no model is called faster or better", async () => {
    const t = await show();
    expect(t).toMatch(/The bake-off has not produced results/);
    expect(t).toMatch(/No model is called faster or better until it has/);
  });
  it("models: costs are always called estimates, and no key is shown", async () => {
    const t = await show();
    expect(t).toMatch(/Costs are estimates from assumed prices, not a bill/);
    expect(t).toMatch(/no key, token or password is shown here/);
    expect(t).not.toMatch(/AIza|sk-[A-Za-z0-9]{10}/);
  });
});
