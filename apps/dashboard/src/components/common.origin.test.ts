// Owner decision D57 (8 Nov 2026): no "synthetic" or "simulated" tag, badge, chip or label anywhere in the app. The engine's origin "synthetic" draws no
// badge; "example data" (a fixture drawn because a service did not answer) and "real" keep their honest words; the one plain line about where numbers come
// from sits in the closed "About this data" disclosure and in the footer of an admin chart. Static markup, no DOM needed.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { AnalyticMeta } from "../types";
import { originLine, originShort, originWords } from "../lib/evidence";
import { ChartFoot, ExampleBadge, OriginBadge, workerOriginLabel } from "./common";

const meta = (origin: string): AnalyticMeta => ({ origin, n: 12, n_unit: "people", split: "held-out people", interval_level: 0.95, note: null, generated_at: "" }) as unknown as AnalyticMeta;
const html = (el: ReturnType<typeof createElement>) => renderToStaticMarkup(el);
const BANNED = /synthetic|simulated/i;

describe("the origin badge", () => {
  it("draws nothing for the engine's synthetic origin, whatever label a screen passes", () => {
    expect(html(createElement(OriginBadge, { meta: meta("synthetic") }))).toBe("");
    expect(html(createElement(OriginBadge, { meta: meta("synthetic"), always: true }))).toBe("");
    expect(html(createElement(OriginBadge, { meta: meta("synthetic"), label: "Some label" }))).toBe("");
    expect(html(createElement(OriginBadge, { meta: meta("synthetic"), label: workerOriginLabel("synthetic") }))).toBe("");
  });

  it("draws nothing for a mixed origin either", () => {
    expect(html(createElement(OriginBadge, { meta: meta("mixed"), always: true }))).toBe("");
    expect(workerOriginLabel("mixed")).toBe("");
    expect(workerOriginLabel("synthetic")).toBe("");
  });

  it("keeps the honest words for real data and for a study that has not run", () => {
    expect(html(createElement(OriginBadge, { meta: meta("real") }))).toBe("");
    expect(html(createElement(OriginBadge, { meta: meta("real"), always: true }))).toContain(">Real<");
    expect(html(createElement(OriginBadge, { meta: meta("unknown") }))).toContain(">Not run<");
    expect(workerOriginLabel("real")).toBe("Real data");
    expect(workerOriginLabel("unknown")).toBe("Not run");
  });

  it("keeps the words of the example-data badge", () => {
    const out = html(createElement(ExampleBadge, { why: { kind: "offline", message: "The engine is not running, so Knack shows example data.", status: 0, code: null } }));
    expect(out).toContain("Example data");
    expect(out).not.toMatch(BANNED);
  });
});

describe("where the numbers come from, in plain words", () => {
  it("says it concretely, without the two words", () => {
    for (const origin of ["real", "synthetic", "mixed", "unknown"]) {
      expect(originLine(origin)).not.toMatch(BANNED);
      expect(originShort(origin) ?? "").not.toMatch(BANNED);
      expect(originWords(origin).text).not.toMatch(BANNED);
      expect(originWords(origin).sr).not.toMatch(BANNED);
    }
    expect(originLine("synthetic")).toMatch(/example people made for this build/);
    expect(originLine("synthetic")).toMatch(/not from real workers/);
    expect(originShort("real")).toBeNull();
  });

  it("is printed inside the closed About this data disclosure on a worker screen, with no tag beside it", () => {
    const out = html(createElement(ChartFoot, { meta: meta("synthetic"), variant: "about" }));
    expect(out).toContain("About this data");
    expect(out).toContain("example people made for this build");
    expect(out).not.toContain("pill--origin");
    expect(out).not.toMatch(BANNED);
  });

  it("is printed as a plain phrase in the footer of an admin chart, with no tag beside it", () => {
    const out = html(createElement(ChartFoot, { meta: meta("synthetic") }));
    expect(out).toContain("data from");
    expect(out).toContain("example people made for this build");
    expect(out).not.toContain("pill--origin");
    expect(out).not.toMatch(BANNED);
  });

  it("adds nothing about origin to the footer of real data beyond the badge a worker asked for", () => {
    const out = html(createElement(ChartFoot, { meta: meta("real") }));
    expect(out).not.toContain("data from");
    expect(out).toContain("pill--origin");
  });
});
