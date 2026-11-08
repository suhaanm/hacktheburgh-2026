import { describe, expect, it } from "vitest";
import type { Fallback } from "../../lib/fallback";
import type { AnalyticMeta } from "../../types";
import { distinctWhys, originOf } from "./Origin";

const meta = (origin: string): AnalyticMeta => ({ origin, n: 1, n_unit: "people", split: null, interval_level: 0.95, note: null, generated_at: "" } as unknown as AnalyticMeta);
const why: Fallback = { kind: "offline", status: 0, code: null, message: "The engine is not running, so this screen shows example data." };

describe("the one origin badge keeps two facts apart", () => {
  it("real data from a live engine carries no badge", () => {
    expect(originOf([{ meta: meta("real") }, { meta: meta("real") }])).toBeNull();
    expect(originOf([{ meta: null }, { meta: meta("real") }])).toBeNull();
    expect(originOf([])).toBeNull();
  });
  it("a live answer about generated people carries no badge at all: no tag, whoever the people are", () => {
    expect(originOf([{ meta: meta("synthetic") }, { meta: meta("synthetic") }])).toBeNull();
    expect(originOf([{ meta: meta("real") }, { meta: meta("synthetic") }])).toBeNull();
    expect(originOf([{ meta: meta("mixed") }])).toBeNull();
  });
  it("a source that fell back to the built-in sample is example data, whatever its fixture meta says", () => {
    const o = originOf([{ meta: meta("synthetic"), why }]);
    expect(o?.text).toBe("Example data");
    expect(o?.data).toBe("example");
    expect(o?.why).toBe(why);
  });
  it("a mix says so: some example data when only some sources fell back", () => {
    expect(originOf([{ meta: meta("real") }, { meta: meta("synthetic"), why }])).toMatchObject({ text: "Some example data", data: "mixed", why });
  });
  it("each different reason is kept once, in order, so one failing source is not blamed for another's reason", () => {
    const off: Fallback = { kind: "extension_off", status: 404, code: "extension_off", message: "This feature is switched off in The engine. Start it with UNDERSTUDY_X_PRIVACY=1 (or UNDERSTUDY_X=1 for every extension) to see your own data." };
    expect(distinctWhys([{ why }, { why }, { why: off }, { meta: meta("real") }]).map((w) => w.kind)).toEqual(["offline", "extension_off"]);
    expect(distinctWhys([{ meta: meta("real") }])).toEqual([]);
    expect(distinctWhys(Array.from({ length: 6 }, (_, i) => ({ why: { ...why, message: `m${i}` } }))).length).toBe(3);
  });
  it("a source with no meta of its own (the memory file) does not turn real data into a mix", () => {
    expect(originOf([{ meta: null }, { meta: meta("real") }])).toBeNull();
    expect(originOf([{ meta: null, why }, { meta: meta("real") }])?.text).toBe("Some example data");
  });
});
