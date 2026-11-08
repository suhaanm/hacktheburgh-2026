// Owner decision D57 and its clarification (8 Nov 2026): no tag, chip, pill, badge or label of ANY wording says that data was generated or made up. The engine's
// origin "synthetic" (or "mixed") draws nothing; "example data" (a fixture drawn because a service did not answer) and "real" keep their honest words. The one
// plain sentence about where numbers come from sits inside the closed "About this data" disclosure (originLine), and on the Evidence page (reviewers). Static
// markup, no DOM needed.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { AnalyticMeta } from "../types";
import { isGenerated, originLine, originWords } from "../lib/evidence";
import { ChartFoot, ExampleBadge, OriginBadge, workerOriginLabel } from "./common";

const meta = (origin: string): AnalyticMeta => ({ origin, n: 12, n_unit: "people", split: "held-out people", interval_level: 0.95, note: null, generated_at: "" }) as unknown as AnalyticMeta;
const html = (el: ReturnType<typeof createElement>) => renderToStaticMarkup(el);
const BANNED = /synthetic|simulated|made[- ]up/i;
/** The markup with every closed <details> removed: what is on the page before anyone opens anything. */
const visible = (markup: string) => markup.replace(/<details[\s\S]*?<\/details>/g, "");

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
  it("says it concretely, without the banned words", () => {
    for (const origin of ["real", "synthetic", "mixed", "unknown"]) {
      expect(originLine(origin)).not.toMatch(BANNED);
      expect(originWords(origin).text).not.toMatch(BANNED);
      expect(originWords(origin).sr).not.toMatch(BANNED);
    }
    expect(originLine("synthetic")).toMatch(/example people made for this build/);
    expect(originLine("synthetic")).toMatch(/not from real workers/);
    expect(isGenerated("synthetic") && isGenerated("mixed") && !isGenerated("real") && !isGenerated("unknown")).toBe(true);
  });

  it("is printed inside the closed About this data disclosure on a worker screen, with no tag beside it", () => {
    const out = html(createElement(ChartFoot, { meta: meta("synthetic"), variant: "about" }));
    expect(out).toContain("About this data");
    expect(out).toContain("example people made for this build");
    expect(out).not.toContain("pill--origin");
    expect(out).not.toMatch(BANNED);
    expect(visible(out)).not.toContain("example people");
  });

  it("is inside a closed About this data in the footer of an admin chart too, and nowhere else on the footer", () => {
    const out = html(createElement(ChartFoot, { meta: meta("synthetic") }));
    expect(out).toContain("About this data");
    expect(out).toContain("example people made for this build");
    expect(out).not.toContain("pill--origin");
    expect(out).not.toMatch(BANNED);
    expect(visible(out)).not.toMatch(/example people|generated|made for this build/);
    expect(visible(out)).toContain("n = ");
  });

  it("adds nothing about origin to the footer of real data beyond the badge a worker asked for", () => {
    const out = html(createElement(ChartFoot, { meta: meta("real") }));
    expect(out).not.toContain("About this data");
    expect(out).toContain("pill--origin");
  });
});
