import { describe, expect, it } from "vitest";
import { makeEvent, validateEvent } from "../src/shared/events";
import { validateAgainstEventSchema } from "./helpers";

const base = () => ({
  schema: 1, id: "6f1d2b9a-0c47-4a38-9a51-2d1b7e8f5c01", t: "2026-11-07T14:03:11.123Z", origin: "real", actor: "human",
  person: "p_9f3a", role: "benefits-processor", source: "browser", type: "click",
  target: { role: "button", label_hash: "h:9f2c1a2b3c4d", domain_hash: "d:77aa00112233" }, meta: { depth_bin: 3, zone: "calc_result" },
}) as Record<string, any>;

describe("validateEvent agrees with the real JSON Schema", () => {
  const mutations: [string, (e: Record<string, any>) => void][] = [
    ["good", () => {}],
    ["no meta", (e) => delete e.meta],
    ["no target", (e) => delete e.target],
    ["bad schema", (e) => (e.schema = 2)],
    ["short id", (e) => (e.id = "abc")],
    ["bad time", (e) => (e.t = "yesterday")],
    ["bad origin", (e) => (e.origin = "fake")],
    ["bad person", (e) => (e.person = "9f3a")],
    ["bad role", (e) => (e.role = "Benefits")],
    ["bad source", (e) => (e.source = "web")],
    ["bad type", (e) => (e.type = "keypress")],
    ["extra key", (e) => (e.url = "https://evil.example")],
    ["target extra key", (e) => (e.target.text = "hello")],
    ["target role upper", (e) => (e.target.role = "Button")],
    ["bad label hash", (e) => (e.target.label_hash = "h:xyz")],
    ["bad domain hash", (e) => (e.target.domain_hash = "example.org")],
    ["meta url", (e) => (e.meta.zone = "https://evil.example/x")],
    ["meta text with spaces", (e) => (e.meta.zone = "hello world")],
    ["meta nested", (e) => (e.meta.x = { a: 1 })],
    ["meta bad key", (e) => (e.meta["Bad Key"] = 1)],
    ["meta null", (e) => (e.meta.x = null)],
    ["meta 17 keys", (e) => { for (let i = 0; i < 17; i++) e.meta[`k${i}`] = i; }],
    ["task id ok", (e) => (e.task_id = "t_204")],
    ["task id bad", (e) => (e.task_id = "204")],
    ["synthetic origin", (e) => (e.origin = "synthetic")],
    ["agent actor", (e) => (e.actor = "agent")],
  ];
  it.each(mutations)("%s", (_name, mutate) => {
    const e = base();
    mutate(e);
    const ajvOk = validateAgainstEventSchema(e) as boolean;
    expect(validateEvent(e) === null, JSON.stringify(validateAgainstEventSchema.errors)).toBe(ajvOk);
  });
});

describe("makeEvent", () => {
  const deps = { now: () => Date.UTC(2026, 10, 7, 14, 3, 11, 123), uuid: () => "6f1d2b9a-0c47-4a38-9a51-2d1b7e8f5c01" };
  it("wraps a record into a schema-valid L0 event", () => {
    const ev = makeEvent({ type: "click", target: { role: "button", domain_hash: "d:77aa00112233" }, meta: { zone: "household_form" } }, { person: "p_9f3a", role: "benefits-processor" }, deps)!;
    expect(ev.t).toBe("2026-11-07T14:03:11.123Z");
    expect(ev.origin).toBe("real");
    expect(ev.actor).toBe("human");
    expect(ev.source).toBe("browser");
    expect(validateAgainstEventSchema(ev)).toBe(true);
  });
  it("refuses a record that would be invalid, rather than sending it", () => {
    expect(makeEvent({ type: "click", meta: { zone: "has spaces and text" } }, { person: "p_9f3a", role: "x1" }, deps)).toBeNull();
    expect(makeEvent({ type: "click" }, { person: "", role: "benefits-processor" }, deps)).toBeNull();
  });
});

import { normaliseConfig } from "../src/shared/config";
import { DEFAULT_CONFIG } from "../src/shared/types";

describe("config: flush_ms and accept_synthetic", () => {
  it("defaults leave behaviour unchanged: 2000 ms, synthetic input not accepted", () => {
    expect(DEFAULT_CONFIG.flush_ms).toBe(2000);
    expect(DEFAULT_CONFIG.accept_synthetic).toBe(false);
    expect(normaliseConfig({})).toMatchObject({ flush_ms: 2000, accept_synthetic: false });
    expect(normaliseConfig(undefined)).toMatchObject({ flush_ms: 2000, accept_synthetic: false });
  });
  it("takes a sensible flush_ms and refuses nonsense", () => {
    expect(normaliseConfig({ flush_ms: 1000 }).flush_ms).toBe(1000);
    expect(normaliseConfig({ flush_ms: 100 }).flush_ms).toBe(100);
    expect(normaliseConfig({ flush_ms: 10000 }).flush_ms).toBe(10000);
    for (const bad of [0, 50, 99, 10001, -5, 1.5, "1000", null, NaN, Infinity]) expect(normaliseConfig({ flush_ms: bad }).flush_ms, String(bad)).toBe(2000);
  });
  it("accept_synthetic is true only for the boolean true", () => {
    expect(normaliseConfig({ accept_synthetic: true }).accept_synthetic).toBe(true);
    for (const bad of [1, "true", "yes", null, {}]) expect(normaliseConfig({ accept_synthetic: bad }).accept_synthetic).toBe(false);
  });
});
