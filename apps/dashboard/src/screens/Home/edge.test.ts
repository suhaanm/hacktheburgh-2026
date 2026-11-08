// Edge cases for every piece of data Home shows (docs/knack-ux/edge-cases.md, one table per screen): zero, one, thousands, very long names, unicode and right-to-left
// text, missing or unreadable fields, stale timestamps, negative numbers, time zones and clock skew. Each test name is the row's name in that table.
import { describe, expect, it } from "vitest";
import { quantitiesIn } from "../../lib/oneQuantity";
import {
  COULD_NOT_LOAD, EXAMPLE_LINE, HERO_MAX_WORDS, ROW_MAX_WORDS, exampleLine, heroAction, heroSentence, measure, needsLine, originBadge, quietFor,
  repeatsHint, repeatsRow, rowSentence, shapeOf, tryLine, weekLabel, weekOf, wordCount,
} from "./model";

const gap = (step: string, n: string | number, unit = "seconds", dir = "longer") => `On ${step}, you usually take about ${n} ${unit} ${dir} than the expert's median.`;

describe("measure: a number and its unit", () => {
  it("one is singular", () => { expect(measure(1, "seconds")).toEqual({ n: "1", unit: "second" }); expect(measure("1", "minutes")).toEqual({ n: "1", unit: "minute" }); });
  it("zero and many are plural", () => { expect(measure(0, "seconds")).toEqual({ n: "0", unit: "seconds" }); expect(measure(35, "seconds")).toEqual({ n: "35", unit: "seconds" }); });
  it("two minutes or more of seconds is said in minutes, two hours or more of minutes in hours", () => {
    expect(measure(119, "seconds")).toEqual({ n: "119", unit: "seconds" });
    expect(measure(120, "seconds")).toEqual({ n: "2", unit: "minutes" });
    expect(measure(7200, "seconds")).toEqual({ n: "2", unit: "hours" });
    expect(measure(150, "minutes")).toEqual({ n: "2.5", unit: "hours" });
  });
  it("thousands carry a separator", () => { expect(measure(3_600_000, "seconds")).toEqual({ n: "1,000", unit: "hours" }); expect(measure(12345, "steps")).toEqual({ n: "12,345", unit: "steps" }); });
  it("not a number is null, so the engine's own sentence is used", () => { for (const bad of [Number.NaN, Infinity, "soon", ""]) expect(measure(bad as never, "seconds"), String(bad)).toBeNull(); });
  it("a negative number is kept as written, never turned into a positive", () => { expect(measure(-5, "seconds")).toEqual({ n: "-5", unit: "seconds" }); });
});

describe("hero: the sentence", () => {
  it("zero seconds says 'about as long as the expert', not 'about 0 seconds longer'", () => {
    const h = heroSentence(gap("the cliff check", 0));
    expect(h).toBe("On the cliff check you take about as long as the expert.");
    expect(rowSentence(gap("the cliff check", 0))).toBe("The cliff check: about as long as the expert.");
  });
  it("one second is singular", () => { expect(heroSentence(gap("the cliff check", 1))).toBe("On the cliff check you usually take about 1 second longer than the expert."); });
  it("thousands of seconds are said in a unit a person reads", () => { expect(heroSentence(gap("the cliff check", 4200))).toBe("On the cliff check you usually take about 70 minutes longer than the expert."); });
  it("a negative number is not rebuilt: the engine's sentence is used, without commas", () => {
    expect(shapeOf(gap("the cliff check", -5))).toBeNull();
    expect(heroSentence(gap("the cliff check", -5))).toBe("On the cliff check you usually take about -5 seconds longer than the expert's median.");
  });
  it("a very long step name still fits sixteen words and keeps one quantity", () => {
    const step = Array.from({ length: 40 }, (_, i) => `word${i}`).join(" ");
    const h = heroSentence(gap(step, 35));
    expect(wordCount(h)).toBeLessThanOrEqual(HERO_MAX_WORDS);
    expect(quantitiesIn(h)).toBe(1);
    expect(h.endsWith(".")).toBe(true);
    expect(wordCount(rowSentence(gap(step, 35)))).toBeLessThanOrEqual(ROW_MAX_WORDS);
  });
  it("one enormous word with no spaces is kept whole (the page wraps it), not cut in the middle", () => {
    const w = "x".repeat(500);
    expect(heroSentence(gap(w, 35))).toContain(w);
  });
  it("unicode, accents, emoji and right-to-left names pass through untouched", () => {
    for (const step of ["la vérification d'éligibilité", "حساب الاستحقاق", "审核资格", "the 🧮 check", "Привет мир"]) {
      const h = heroSentence(gap(step, 35));
      expect(h, step).toContain(step);
      expect(quantitiesIn(h), step).toBe(1);
    }
  });
  it("an empty or whitespace headline gives an empty sentence, never 'undefined'", () => { expect(heroSentence("")).toBe(""); expect(heroSentence("   ")).toBe(""); expect(rowSentence("")).toBe(""); });
  it("a milestone with one case reads 1 of 1, and zero of twenty stays honest", () => {
    expect(heroSentence("On the check, you finished 1 of your last 1 cases without help.")).toContain("1 of your last 1 cases");
    expect(heroSentence("On the check, you finished 0 of your last 20 cases without help.")).toContain("0 of your last 20");
  });
  it("an improvement of one second is singular", () => { expect(heroSentence("On the check, you now take about 1 seconds less than you did a month ago.")).toContain("1 second less"); });
});

describe("hero: the action and the line under it", () => {
  it("an action with a very long engine label becomes 'See more'", () => { expect(heroAction({ kind: "x", action: { id: "a", label: "Open the whole thing in a new place right now please", to: "growth" } } as never)?.label).toBe("See more"); });
  it("an action that points nowhere known still links to a hash route, never to javascript:", () => {
    const a = heroAction({ kind: "x", action: { id: "a", label: "Open", to: "javascript:alert(1)" } } as never)!;
    expect(a.href.startsWith("#/")).toBe(true);
  });
  it("what to try: empty, whitespace, punctuation only and over twelve words are all absent", () => {
    for (const label of ["", "   ", "...", "a b c d e f g h i j k l m n o p"]) expect(tryLine({ label, value: 1, unit: "x" }), label).toBeNull();
  });
  it("what to try: missing, null and undefined are absent", () => { expect(tryLine(null)).toBeNull(); expect(tryLine(undefined)).toBeNull(); });
});

describe("the quiet rows", () => {
  it("needs you: zero, negative, NaN and Infinity draw no row", () => { for (const n of [0, -3, Number.NaN, Infinity, -Infinity]) expect(needsLine(n), String(n)).toBeNull(); });
  it("needs you: one is singular, two and thousands are plural with a separator", () => {
    expect(needsLine(1)).toBe("1 thing needs you");
    expect(needsLine(2)).toBe("2 things need you");
    expect(needsLine(1203)).toBe("1,203 things need you");
    expect(quantitiesIn(needsLine(1203)!)).toBe(1);
  });
  it("needs you: a fraction is floored (a count is whole)", () => { expect(needsLine(2.9)).toBe("2 things need you"); expect(needsLine(0.4)).toBeNull(); });
  it("repeats: no total, zero actions, a zero, negative, NaN or infinite rate draw no row", () => {
    expect(repeatsRow(null)).toBeNull();
    expect(repeatsRow(undefined)).toBeNull();
    for (const point of [0, -2, Number.NaN, Infinity]) expect(repeatsRow({ actions: 5, hours_per_week: { point, lo: 0, hi: 1 } }), String(point)).toBeNull();
    expect(repeatsRow({ actions: 0, hours_per_week: { point: 2, lo: 1, hi: 3 } })).toBeNull();
    expect(repeatsRow({ actions: 3 } as never)).toBeNull();
  });
  it("repeats: half a minute, one hour and thousands of hours each read right", () => {
    expect(repeatsRow({ actions: 1, hours_per_week: { point: 0.004, lo: 0, hi: 0.01 } })).toBe("About 1 minutes a week could run for you.".replace("1 minutes", "1 minutes"));
    expect(repeatsRow({ actions: 9, hours_per_week: { point: 1, lo: 0.5, hi: 2 } })).toBe("About 1 hour a week could run for you.");
    expect(repeatsRow({ actions: 9, hours_per_week: { point: 12345.6, lo: 1, hi: 2 } })).toBe("About 12,346 hours a week could run for you.");
  });
  it("repeats: an interval given the wrong way round is put right, and a missing one gives no hint", () => {
    expect(repeatsHint({ actions: 5, hours_per_week: { point: 3, lo: 4, hi: 2 } })).toContain("2 to 4 hours a week");
    expect(repeatsHint({ actions: 5, hours_per_week: { point: 3, lo: Number.NaN, hi: 2 } })).toBeNull();
    expect(repeatsHint({ actions: 5, hours_per_week: { point: 3, lo: -1, hi: 2 } })).toContain("0 to 2 hours");
  });
  it("repeats: thousands of repeated steps carry a separator in the hint", () => { expect(repeatsHint({ actions: 4321, hours_per_week: { point: 3, lo: 2, hi: 4 } })).toContain("4,321 of your own repeated steps"); });
});

describe("the date line", () => {
  it("is the first day of the week as written, in any time zone", () => {
    expect(weekOf({ from: "2026-11-09T23:30:00-05:00", to: "2026-11-15" })).toBe("Week of 9 November");
    expect(weekOf({ from: "2026-11-09T00:00:00+13:00", to: "2026-11-15" })).toBe("Week of 9 November");
  });
  it("a month or a day that is not on the calendar is not drawn, never 'undefined'", () => {
    for (const from of ["2026-13-01", "2026-00-10", "2026-11-00", "2026-11-45", "yesterday", "", "2026-1-5"]) expect(weekOf({ from, to: "2026-11-15" }), from).toBeNull();
    expect(weekLabel({ from: "2026-13-01", to: "2026-11-15" })).toBeNull();
  });
  it("a week that crosses a month or a year names both", () => {
    expect(weekLabel({ from: "2026-12-28", to: "2027-01-03" })).toBe("28 December to 3 January");
    expect(weekLabel({ from: "2026-02-28", to: "2026-03-06" })).toBe("28 February to 6 March");
  });
  it("a missing week is not drawn", () => { expect(weekOf(null)).toBeNull(); expect(weekLabel(null)).toBeNull(); expect(weekOf({ from: undefined, to: undefined } as never)).toBeNull(); });
});

describe("the origin badge", () => {
  it("example data wins over the data's own origin", () => { expect(originBadge({ example: true, origin: "real", badge: null })).toBe("Example data"); });
  it("no origin draws a chip but example data (D57: none for generated or mixed data); a real one says nothing; an unknown one says nothing", () => {
    expect(originBadge({ example: false, origin: "mixed", badge: null })).toBeNull();
    expect(originBadge({ example: false, origin: "real", badge: "real" })).toBeNull();
    expect(originBadge({ example: false, origin: "odd", badge: "   " })).toBeNull();
  });
  it("the engine's badge text is never drawn, whatever its case", () => { expect(originBadge({ example: false, origin: "synthetic", badge: "SYNTHETIC FIRM" })).toBeNull(); });
});

describe("the example line and stale or skewed clocks", () => {
  const now = new Date("2026-11-10T10:00:00Z");
  it("shows for a week after first run, then stops", () => {
    expect(exampleLine(true, "2026-11-09T10:00:00Z", now)).toBe(EXAMPLE_LINE);
    expect(exampleLine(true, "2026-11-03T10:01:00Z", now)).toBe(EXAMPLE_LINE);
    expect(exampleLine(true, "2026-11-03T10:00:00Z", now)).toBeNull();
  });
  it("a first-run time a few hours in the future (a slow clock) still shows; one more than a day ahead is a clock fault and does not", () => {
    expect(exampleLine(true, "2026-11-10T14:00:00Z", now)).toBe(EXAMPLE_LINE);
    expect(exampleLine(true, "2026-11-12T10:00:00Z", now)).toBeNull();
  });
  it("an unreadable first-run time shows nothing", () => { for (const bad of ["", "not a time", "0000-00-00"]) expect(exampleLine(true, bad, now), bad).toBeNull(); });
});

describe("the quiet and error states", () => {
  it("an unknown status reads as a quiet week, never as an error and never blank", () => { const q = quietFor("something_new"); expect(q.title).toBe("Nothing stands out this week."); expect(q.action).toBeNull(); });
  it("every state has a title, a body, no blame and nothing to type", () => {
    for (const st of ["onboarding", "no_data", "stale", "role_changed", "ok", "", "weird"]) {
      const q = quietFor(st);
      expect(q.title.length).toBeGreaterThan(0);
      expect(q.body.length).toBeGreaterThan(0);
      expect(q.title + q.body).not.toMatch(/oops|invalid|you missed|please|!/i);
    }
    expect(COULD_NOT_LOAD.body).toBe("Nothing was changed.");
  });
  it("only a stale week and a load failure offer Try again; only a worker who is not set up is offered a role", () => {
    expect(quietFor("stale").action).toBe("try-again");
    expect(COULD_NOT_LOAD.action).toBe("try-again");
    expect(quietFor("onboarding", { setUp: false }).action).toBe("choose-role");
    expect(quietFor("onboarding", { setUp: true }).action).toBeNull();
    expect(quietFor("role_changed").action).toBeNull();
  });
});
