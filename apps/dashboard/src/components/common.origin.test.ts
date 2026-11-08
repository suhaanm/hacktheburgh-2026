// Owner rule (8 Nov 2026): no screen carries a pill, chip, badge, banner or sentence that says or implies what is on screen is example data, a stand-in or made up,
// and none says "real" either. The chart footer prints n, split, interval level and the author's own note, and nothing about where the numbers came from. Static markup,
// no DOM needed.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { AnalyticMeta } from "../types";
import * as common from "./common";
import { ChartFoot } from "./common";

const meta = (origin: string): AnalyticMeta => ({ origin, n: 12, n_unit: "people", split: "held-out people", interval_level: 0.95, note: null, generated_at: "" }) as unknown as AnalyticMeta;
const html = (el: ReturnType<typeof createElement>) => renderToStaticMarkup(el);
const TAGS = /example|sample|stand[- ]in|made[- ]up|synthetic|simulated|not real workers|for this build|pill--origin|where from/i;

describe("no origin tag anywhere", () => {
  it("the components that drew a tag are gone", () => {
    for (const name of ["ExampleBadge", "OriginBadge", "SourceNote", "workerOriginLabel"]) expect(name in common, name).toBe(false);
  });

  it("the footer of a worker chart says n, split and intervals, and never where the numbers came from", () => {
    for (const origin of ["real", "synthetic", "mixed", "unknown"]) {
      const out = html(createElement(ChartFoot, { meta: meta(origin), variant: "about" }));
      expect(out).toContain("About this data");
      expect(out).not.toMatch(TAGS);
    }
  });

  it("the footer of an admin chart prints n, split and intervals, and nothing about origin", () => {
    for (const origin of ["real", "synthetic", "mixed", "unknown"]) {
      const out = html(createElement(ChartFoot, { meta: meta(origin) }));
      expect(out).toContain("n = ");
      expect(out).not.toContain("About this data");
      expect(out).not.toMatch(TAGS);
    }
  });
});
