import { describe, expect, it } from "vitest";
import { exampleFirm, exampleHitlist } from "./repeats";

describe("the example week", () => {
  it("is ranked by minutes, never lists a row under three repeats, and carries intervals around every point", () => {
    for (const w of [7, 30] as const) {
      const d = exampleHitlist(w);
      expect(d.state).toBe("ok");
      const pts = d.rows.map((r) => r.minutes_per_week.point);
      expect([...pts].sort((a, b) => b - a)).toEqual(pts);
      for (const r of d.rows) {
        expect(r.count).toBeGreaterThanOrEqual(3);
        expect(r.minutes_per_week.lo).toBeLessThanOrEqual(r.minutes_per_week.point);
        expect(r.minutes_per_week.hi).toBeGreaterThanOrEqual(r.minutes_per_week.point);
        expect(r.key === null || r.label.toLowerCase().includes(r.key.toLowerCase())).toBe(true);
      }
      expect(d.rows.length).toBeLessThanOrEqual(10);
      expect(d.total?.actions).toBe(d.rows.length);
    }
  });
  it("has seven or more rows in a week so Show all has something to show, one chip each kind, and an automated fold", () => {
    const d = exampleHitlist(7);
    expect(d.rows.length).toBeGreaterThan(7);
    expect(new Set(d.rows.map((r) => r.status))).toEqual(new Set(["proposed", "learning", "running", "candidate"]));
    expect(d.automated).toHaveLength(1);
    expect(d.automated[0].status).toBe("automated");
    expect(d.held_back.length).toBeGreaterThan(0);
  });
  it("applies what the worker did this session: hide, start counting again, watch first", () => {
    const hid = exampleHitlist(7, { hidden: new Set(["calc-entry-3x"]) });
    expect(hid.rows.some((r) => r.id === "calc-entry-3x")).toBe(false);
    expect(hid.hidden.some((h) => h.id === "calc-entry-3x" && h.returns_at === h.count * 2)).toBe(true);
    const reset = exampleHitlist(7, { reset: true });
    expect(reset.state).toBe("counting_again");
    expect(reset.rows).toEqual([]);
    expect(reset.counting_since).not.toBeNull();
    const watching = exampleHitlist(7, { status: { "reconcile-totals": "learning" } });
    expect(watching.rows.find((r) => r.id === "reconcile-totals")?.status).toBe("learning");
  });
  it("has a plain sentence for every empty state", () => {
    for (const kind of ["new_user", "too_little_data", "nothing_repeats", "all_handled", "counting_again", "capture_off"] as const) {
      const d = exampleHitlist(7, { kind });
      expect(d.state).toBe(kind);
      expect(d.rows).toEqual([]);
      expect(d.message.length).toBeGreaterThan(20);
      expect(d.total).toBeNull();
    }
    expect(exampleHitlist(7, { kind: "too_little_data" }).message).toContain("30 day view");
    expect(exampleHitlist(30, { kind: "too_little_data" }).message).not.toContain("30 day view");
  });
});

describe("the example firm", () => {
  it("lists only groups of five or more, names no one, and orders by time", () => {
    const f = exampleFirm(7);
    expect(f.people).toBe(60);
    expect(f.rows.every((r) => r.people >= f.min_group)).toBe(true);
    const h = f.rows.map((r) => r.hours_per_week.point);
    expect([...h].sort((a, b) => b - a)).toEqual(h);
    expect(JSON.stringify(f)).not.toMatch(/person_|"person"/);
    for (const r of f.rows) expect(r.hours_per_week.lo).toBeLessThanOrEqual(r.hours_per_week.hi);
  });
});
