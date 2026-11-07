import { describe, expect, it } from "vitest";
import type { Fallback } from "../../lib/fallback";
import type { AnalyticMeta } from "../../types";
import { originOf } from "./Origin";

const meta = (origin: string): AnalyticMeta => ({ origin, n: 1, n_unit: "people", split: null, interval_level: 0.95, note: null, generated_at: "" } as unknown as AnalyticMeta);
const why: Fallback = { kind: "offline", status: 0, code: null, message: "The engine is not running, so this screen shows example data." };

describe("the one origin badge keeps two facts apart", () => {
  it("real data from a live engine carries no badge", () => {
    expect(originOf([{ meta: meta("real") }, { meta: meta("real") }])).toBeNull();
    expect(originOf([{ meta: null }, { meta: meta("real") }])).toBeNull();
    expect(originOf([])).toBeNull();
  });
  it("a live answer whose meta says synthetic is a synthetic firm, not example data", () => {
    const o = originOf([{ meta: meta("synthetic") }, { meta: meta("synthetic") }]);
    expect(o).toEqual({ text: "Synthetic firm", data: "synthetic", why: null });
    expect(o?.text).not.toMatch(/example/i);
  });
  it("a source that fell back to the built-in sample is example data, whatever its fixture meta says", () => {
    const o = originOf([{ meta: meta("synthetic"), why }]);
    expect(o?.text).toBe("Example data");
    expect(o?.data).toBe("example");
    expect(o?.why).toBe(why);
  });
  it("a mix says so: some example data when one source fell back, some synthetic data when live sources differ", () => {
    expect(originOf([{ meta: meta("real") }, { meta: meta("synthetic"), why }])).toMatchObject({ text: "Some example data", data: "mixed", why });
    expect(originOf([{ meta: meta("real") }, { meta: meta("synthetic") }])).toEqual({ text: "Some synthetic data", data: "mixed", why: null });
  });
  it("a source with no meta of its own (the memory file) does not turn real data into a mix", () => {
    expect(originOf([{ meta: null }, { meta: meta("synthetic") }])?.text).toBe("Synthetic firm");
  });
});
