import { describe, expect, it } from "vitest";
import { fmtHours, fmtHoursRange, fmtMinutes, fmtRange, heldText, ledeFor, minutesExplained, moveIndex, peopleText, plainGate, shownRows, splitKey, timesText, totalExplained } from "./model";
import type { HitRow } from "./types";

const row = (over: Partial<HitRow> = {}): HitRow => ({
  id: "calc-entry-3x", label: "Enter the household into three calculators", key: "household", family: "enter", count: 16, minutes_per_week: { point: 56.4, lo: 32.4, hi: 87.3 },
  judgement_share: 0.1, status: "candidate", stops_before: "submit", variation: 0.05, variants: 1, overlaps: [], seconds_per_time: 232, t: 1, actions: { routine_id: "calc-entry-3x", can_automate: true, card_id: "c_x" },
  what: "", touches: [], never: [], ...over,
});

describe("figures always carry their unit", () => {
  it("minutes become hours past a hundred, with no trailing zeros", () => {
    expect(fmtMinutes(14.2)).toBe("14 min");
    expect(fmtMinutes(56.4)).toBe("56 min");
    expect(fmtMinutes(99.4)).toBe("99 min");
    expect(fmtMinutes(114.4)).toBe("1.9 h");
    expect(fmtMinutes(120)).toBe("2 h");
    expect(fmtMinutes(0)).toBe("0 min");
  });
  it("hours keep two decimals only when small", () => {
    expect(fmtHours(0.75)).toBe("0.75 h");
    expect(fmtHours(1.18)).toBe("1.2 h");
    expect(fmtHours(68.43)).toBe("68 h");
    expect(fmtHoursRange({ point: 1.18, lo: 0.75, hi: 1.73 })).toBe("0.8 to 1.7 h");
  });
  it("a range is in the unit its point estimate uses, so the two read together", () => {
    expect(fmtRange({ point: 56.4, lo: 32.4, hi: 87.3 })).toBe("32 to 87 min");
    expect(fmtRange({ point: 114.4, lo: 76.8, hi: 159.9 })).toBe("1.3 to 2.7 h");
  });
  it("counts say time or times, person or people", () => {
    expect(timesText(1)).toBe("1 time");
    expect(timesText(1234)).toBe("1,234 times");
    expect(peopleText(1)).toBe("1 person");
    expect(peopleText(32)).toBe("32 people");
  });
});

describe("labels", () => {
  it("splits around the key, ignoring case, first match only", () => {
    expect(splitKey("Enter the household into three calculators", "household")).toEqual(["Enter the ", "household", " into three calculators"]);
    expect(splitKey("Open calculator, enter household", "Open calculator")).toEqual(["", "Open calculator", ", enter household"]);
    expect(splitKey("Copy the Case Note", "case note")).toEqual(["Copy the ", "Case Note", ""]);
  });
  it("no key, or a key that is not in the label, leaves the label plain", () => {
    expect(splitKey("Do the thing", null)).toEqual(["Do the thing", "", ""]);
    expect(splitKey("Do the thing", "other")).toEqual(["Do the thing", "", ""]);
  });
});

describe("the list", () => {
  it("shows seven until asked for all", () => {
    const rows = Array.from({ length: 9 }, (_, i) => i);
    expect(shownRows(rows, false, 7)).toHaveLength(7);
    expect(shownRows(rows, true, 7)).toHaveLength(9);
    expect(shownRows(rows.slice(0, 7), false, 7)).toHaveLength(7);
  });
  it("arrow keys move, clamp at the ends, and Home and End jump", () => {
    expect(moveIndex(0, "ArrowDown", 3)).toBe(1);
    expect(moveIndex(2, "ArrowDown", 3)).toBe(2);
    expect(moveIndex(0, "ArrowUp", 3)).toBe(0);
    expect(moveIndex(2, "Home", 3)).toBe(0);
    expect(moveIndex(0, "End", 3)).toBe(2);
    expect(moveIndex(0, "Enter", 3)).toBeNull();
    expect(moveIndex(0, "ArrowDown", 0)).toBeNull();
  });
});

describe("words behind the numbers", () => {
  it("explains the minutes with the count, the time a run and the judgement share", () => {
    const t = minutesExplained(row(), 7);
    expect(t).toContain("About 56 min a week, between 32 to 87 min (95% interval)");
    expect(t).toContain("16 times in 7 days at about 3.9 min each, of which 10% is judgement you would still do.");
    expect(minutesExplained(row({ judgement_share: 0, seconds_per_time: 40 }), 30)).toMatch(/at about 40 s each\.$/);
  });
  it("the sentence under the title names the count, the window and the hours", () => {
    expect(ledeFor(2, { point: 1.18, lo: 0.75, hi: 1.73 }, 7)).toBe("2 things you did by hand in the last 7 days, about 1.2 h a week.");
    expect(ledeFor(1, { point: 0.5, lo: 0.4, hi: 0.6 }, 30)).toBe("One thing you did by hand in the last 30 days, about 0.5 h a week.");
    expect(totalExplained(28, 306, { point: 1.18, lo: 0.75, hi: 1.73 }, 7)).toBe("About 1.2 h a week, between 0.8 to 1.7 h (95% interval), from 28 repeats in 306 cases over 7 days.");
  });
  it("says in one line what repeats but is not offered", () => {
    expect(heldText([], 0)).toBe("");
    expect(heldText([{ reason: "judgement", count: 2 }, { reason: "irreversible_first_step", count: 1 }], 0))
      .toBe("3 more repeat but are not offered: 2 need your judgement, 1 begins with a step that cannot be undone.");
    expect(heldText([{ reason: "unstable", count: 1 }], 0)).toBe("1 more repeats but is not offered: 1 varies too much from one time to the next.");
    expect(heldText([], 3)).toBe("3 smaller ones are not shown.");
    expect(heldText([{ reason: "denylist", count: 2 }], 1)).toBe("2 more repeat but are not offered: 2 involve something on your denylist. 1 smaller one is not shown.");
  });
  it("turns the skill gate message into a sentence, and leaves other messages alone", () => {
    expect(plainGate("coach first: ENTER_HOUSEHOLD at L1. Coach it first, or say you already know it.")).toBe("Your skill at enter household is at level 1. Automating starts at level 4.");
    expect(plainGate("something else")).toBe("something else");
  });
});
