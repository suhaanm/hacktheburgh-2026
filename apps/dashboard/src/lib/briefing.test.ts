import { describe, expect, it } from "vitest";
import { checkedNote, fireWhat, rankingParts } from "./briefing";

describe("briefing card wording", () => {
  it("says what the press does for each fire type", () => {
    expect(fireWhat("queue")).toMatch(/approval item.*Nothing runs until you approve/);
    expect(fireWhat("draft")).toMatch(/local draft/);
    expect(fireWhat("agent")).toMatch(/only reads/);
    expect(fireWhat(undefined)).toMatch(/either creates an approval item/);
  });
  it("adds the risk when a card is not normal", () => {
    expect(fireWhat("queue", "irreversible")).toMatch(/cannot be undone/);
    expect(fireWhat("queue", "outward")).toMatch(/outside this laptop/);
    expect(fireWhat("queue", "normal")).not.toMatch(/cannot be undone|outside/);
  });
  it("orders score parts by how much they moved the card, effort counting against it", () => {
    const p = rankingParts({ parts: { value: { x: 0.9, w: 0.35, contribution: 0.315 }, effort: { x: 0.2, w: -0.15, contribution: -0.03 }, urgency: { x: 0.5, w: 0.25, contribution: 0.125 } } });
    expect(p.map((x) => x.key)).toEqual(["value", "urgency", "effort"]);
    expect(p[2].label).toBe("Effort");
    expect(p[2].contribution).toBeLessThan(0);
    expect(rankingParts(undefined)).toEqual([]);
  });
  it("reports what the check found", () => {
    expect(checkedNote({ verdict: "confirmed", verify_note: "Checked just now: still true." })).toBe("Checked just now: still true.");
    expect(checkedNote({ verdict: "confirmed" })).toMatch(/still true/);
    expect(checkedNote({ verdict: "stale" })).toBe("");
  });
});
