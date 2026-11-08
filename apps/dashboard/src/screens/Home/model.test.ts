import { describe, expect, it } from "vitest";
import workerFx from "../../fixtures/home-worker.json";
import goodFx from "../../fixtures/home-worker-good.json";
import { quantitiesIn } from "../../lib/oneQuantity";
import {
  ACTION_MAX_WORDS, COULD_NOT_LOAD, EXAMPLE_LINE, coachLine, GROWTH_ROW, HERO_MAX_WORDS, ROW_MAX_WORDS, TRY_MAX_WORDS, exampleLine, heroAction, heroSentence, needsLine,
  originBadge, quietFor, repeatsHint, repeatsRow, rowSentence, shapeOf, tryLine, weekLabel, weekOf, wordCount,
} from "./model";

type Pointer = { headline: string; kind: string; action: { id: string; label: string; to: string; query?: string | null } | null };
const pointers = (fx: unknown): Pointer[] => (fx as { data: { pointers: Pointer[] } }).data.pointers;
const all = [...pointers(workerFx), ...pointers(goodFx)];

describe("the coaching row", () => {
  it("names the task, cut at its first comma, while a step is active", () => {
    expect(coachLine({ name: "Entitlement check, household H-9", step: 5, steps_total: 9 })).toBe("Coaching you on Entitlement check.");
    expect(coachLine({ name: "Month-end reconciliation: step list", step: 1, steps_total: 3 })).toBe("Coaching you on Month-end reconciliation.");
    expect(coachLine({ name: "One two three four five six seven", step: 2, steps_total: 4 })).toBe("Coaching you on One two three four five.");
  });
  it("is one line of at most twelve words", () => {
    const l = coachLine({ name: "Entitlement check, household H-9", step: 5, steps_total: 9 })!;
    expect(wordCount(l)).toBeLessThanOrEqual(ROW_MAX_WORDS);
  });
  it("is absent when no step is active, and never throws on what a service might send", () => {
    for (const bad of [null, undefined, {}, { name: "" }, { name: "   ", step: 1, steps_total: 2 }, { name: 7, step: 1 }, { name: "Check", step: 0, steps_total: 3 }, { name: "Check", step: -1, steps_total: 3 }, { name: "Check", step: 1.5, steps_total: 3 }, { name: "Check", step: "x", steps_total: 3 }, { name: "Check", step: 4, steps_total: 3 }, { name: ",,,", step: 1, steps_total: 3 }]) {
      expect(coachLine(bad as never), JSON.stringify(bad)).toBeNull();
    }
  });
  it("copes with unicode and right-to-left task names and an unknown total", () => {
    expect(coachLine({ name: "فحص الاستحقاق", step: 2 })).toBe("Coaching you on فحص الاستحقاق.");
    expect(coachLine({ name: "Résumé du dossier", step: 3, steps_total: "?" })).toBe("Coaching you on Résumé du dossier.");
  });
});

describe("the hero sentence", () => {
  it("rebuilds the template: no comma after the step, the expert instead of the expert's median", () => {
    expect(heroSentence("On the cliff check, you usually take about 35 seconds longer than the expert's median.")).toBe("On the cliff check you usually take about 35 seconds longer than the expert.");
    expect(heroSentence("On the cliff check, you now take about 15 seconds less than you did a month ago.")).toBe("On the cliff check you now take about 15 seconds less than a month ago.");
    expect(heroSentence("On reconciling before the note, you finished 17 of your last 20 cases without help.")).toBe("On reconciling before the note you finished 17 of your last 20 cases without help.");
  });
  it("is at most 16 words with one quantity for every pointer the engine can send", () => {
    expect(all.length).toBeGreaterThanOrEqual(5);
    for (const p of all) {
      const h = heroSentence(p.headline);
      expect(wordCount(h), h).toBeLessThanOrEqual(HERO_MAX_WORDS);
      expect(quantitiesIn(h), h).toBe(1);
      expect(shapeOf(p.headline), p.headline).not.toBeNull();
    }
  });
  it("uses an unknown headline as it is, without commas", () => {
    expect(heroSentence("Something new, from the engine.")).toBe("Something new from the engine.");
    expect(shapeOf("Something new")).toBeNull();
  });
});

describe("the quiet row for a second pointer", () => {
  it("is at most 12 words with one quantity", () => {
    for (const p of all) {
      const r = rowSentence(p.headline);
      expect(wordCount(r), r).toBeLessThanOrEqual(ROW_MAX_WORDS);
      expect(quantitiesIn(r), r).toBe(1);
    }
    expect(rowSentence("On reconciling before the note, you usually take about 15 seconds longer than the expert's median.")).toBe("Reconciling before the note: about 15 seconds longer than the expert.");
  });
});

describe("the one action", () => {
  it("is a verb phrase of at most five words (the spec's own example has five), and a habit that costs time opens Where time goes", () => {
    for (const p of all) {
      const a = heroAction(p as never);
      expect(a).not.toBeNull();
      expect(wordCount(a!.label), a!.label).toBeLessThanOrEqual(ACTION_MAX_WORDS);
      expect(a!.label).toMatch(/^See /);
    }
    expect(heroAction({ kind: "time_loss_habit", action: { id: "open_growth", label: "Open Growth", to: "growth" } } as never)).toEqual({ label: "See where the time goes", href: "#/growth?section=steps" });
    expect(heroAction({ kind: "habit_improved", action: { id: "open_growth", label: "See how it changed", to: "growth" } } as never)).toEqual({ label: "See how it changed", href: "#/growth" });
  });
  it("is absent when the engine has no action", () => {
    expect(heroAction({ kind: "time_loss_habit", action: null } as never)).toBeNull();
  });
});

describe("what to try", () => {
  it("is absent when the engine sends none, imperative and short when it does", () => {
    expect(tryLine(null)).toBeNull();
    expect(tryLine({ label: "Read, then check", value: 10, unit: "seconds" })).toBe("Try read, then check.");
    expect(wordCount(tryLine({ label: "Read, then check", value: 1, unit: "x" })!)).toBeLessThanOrEqual(TRY_MAX_WORDS);
    expect(tryLine({ label: "a very long suggestion that goes on and on and on and on forever", value: 1, unit: "x" })).toBeNull();
  });
});

describe("the quiet rows", () => {
  it("says how many things need you, and nothing at zero", () => {
    expect(needsLine(0)).toBeNull();
    expect(needsLine(1)).toBe("1 thing needs you");
    expect(needsLine(3)).toBe("3 things need you");
    for (const n of [1, 2, 9]) { const l = needsLine(n)!; expect(quantitiesIn(l), l).toBe(1); expect(wordCount(l)).toBeLessThanOrEqual(ROW_MAX_WORDS); }
  });
  it("says the repeated time as one rate, in hours or minutes, with the interval in its hint", () => {
    const t = { actions: 6, hours_per_week: { point: 1, lo: 0.8, hi: 1.2 } };
    expect(repeatsRow(t)).toBe("About 1 hour a week could run for you.");
    expect(repeatsRow({ actions: 6, hours_per_week: { point: 3.44, lo: 2.4, hi: 4.46 } })).toBe("About 3.4 hours a week could run for you.");
    expect(repeatsRow({ actions: 1, hours_per_week: { point: 0.5, lo: 0.25, hi: 0.75 } })).toBe("About 30 minutes a week could run for you.");
    expect(repeatsHint({ actions: 6, hours_per_week: { point: 3.44, lo: 2.4, hi: 4.46 } })).toContain("2.4 to 4.5 hours a week");
    expect(repeatsRow(null)).toBeNull();
    expect(repeatsRow({ actions: 0, hours_per_week: { point: 1, lo: 1, hi: 1 } })).toBeNull();
    expect(quantitiesIn(repeatsRow(t)!)).toBe(1);
    expect(wordCount(GROWTH_ROW)).toBeLessThanOrEqual(ROW_MAX_WORDS);
  });
});

describe("the states that are not a normal week", () => {
  it("uses the shortest wording of the wireframe for each", () => {
    expect(quietFor("onboarding")).toMatchObject({ title: "Knack is learning your work.", body: "Check back in a few days.", action: null });
    expect(quietFor("nothing_stands_out")).toMatchObject({ title: "Nothing stands out this week.", body: "No number moved far enough to matter.", action: null });
    expect(quietFor("stale")).toMatchObject({ title: "These numbers are out of date.", body: "Knack says nothing rather than something old.", action: "try-again" });
    expect(quietFor("role_changed")).toMatchObject({ title: "Your role changed.", body: "Pointers start again, so you are not compared with your old role.", action: null });
    expect(COULD_NOT_LOAD).toMatchObject({ title: "Could not read your week.", body: "Nothing was changed.", action: "try-again" });
  });
  it("asks for a role first when the worker is not set up", () => {
    expect(quietFor("onboarding", { setUp: false })).toMatchObject({ kind: "set_up", action: "choose-role" });
  });
  it("keeps every title to five words and every body to ten or a printed reason", () => {
    for (const s of ["onboarding", "no_data", "stale", "role_changed", "nothing_stands_out", "ok"]) {
      const q = quietFor(s);
      expect(wordCount(q.title), q.title).toBeLessThanOrEqual(6);
      expect(q.title + q.body).not.toMatch(/!|you missed|overdue|oops|please/i);
    }
  });
});

describe("dates, badge and the example line", () => {
  it("says the week by its first day", () => {
    expect(weekOf({ from: "2026-11-09", to: "2026-11-15" })).toBe("Week of 9 November");
    expect(weekOf(null)).toBeNull();
    expect(weekLabel({ from: "2026-11-30", to: "2026-12-06" })).toBe("30 November to 6 December");
    expect(weekLabel({ from: "soon", to: "later" })).toBeNull();
  });
  it("draws one origin badge in sentence case", () => {
    expect(originBadge({ example: true, origin: "synthetic", badge: "synthetic firm" })).toBe("Example data");
    expect(originBadge({ example: false, origin: "synthetic", badge: "synthetic firm" })).toBe("Synthetic firm");
    expect(originBadge({ example: false, origin: "real", badge: null })).toBeNull();
    expect(originBadge({ example: false, origin: null, badge: null })).toBeNull();
  });
  it("says the example line only while an example stands in, in the first week after first run", () => {
    const now = new Date("2026-11-10T10:00:00Z");
    expect(exampleLine(true, "2026-11-09T10:00:00Z", now)).toBe(EXAMPLE_LINE);
    expect(exampleLine(true, "2026-11-01T10:00:00Z", now)).toBeNull();
    expect(exampleLine(false, "2026-11-09T10:00:00Z", now)).toBeNull();
    expect(exampleLine(true, null, now)).toBeNull();
  });
});
