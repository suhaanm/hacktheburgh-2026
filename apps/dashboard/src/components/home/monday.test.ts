import { describe, expect, it } from "vitest";
import { mondayNote, noteLines, MONDAY_INTRO } from "./monday";
import type { WirePointer } from "../firm/wire";

const ptr = (id: string, headline: string): WirePointer => ({
  id, kind: "habit", headline, detail: null, numbers: {}, origin: "synthetic", n: null, n_unit: null, polarity: "positive", polarity_label: "Going well",
  glyph: null, a11y_label: null, badge: "synthetic firm", details_available: true, action: null,
});

describe("mondayNote", () => {
  it("is null when there are no pointers and no engine text", () => {
    expect(mondayNote({ pointers: [], try: null, monday_note: null })).toBeNull();
  });
  it("shows the engine's text verbatim when it sends one", () => {
    expect(mondayNote({ pointers: [ptr("a", "x.")], try: null, monday_note: "  Ready text.  " })).toBe("Ready text.");
  });
  it("builds the note from the pointer sentences and fixed words", () => {
    const n = mondayNote({ pointers: [ptr("a", "You took 15 seconds less"), ptr("b", "You finished 17 of 20 without help.")], try: null, monday_note: null });
    expect(n).toBe(`${MONDAY_INTRO(2)} You took 15 seconds less. You finished 17 of 20 without help.`);
  });
  it("uses the singular for one pointer and adds the number to try", () => {
    const n = mondayNote({ pointers: [ptr("a", "One thing.")], try: { label: "Times you used the checklist", value: 3, unit: "times" }, monday_note: null }) ?? "";
    expect(n.startsWith("Knack has 1 pointer for your week.")).toBe(true);
    expect(n.endsWith("One thing to try: times you used the checklist, 3 times.")).toBe(true);
  });
  it("never types a number of its own into the note", () => {
    const n = mondayNote({ pointers: [ptr("a", "Words only")], try: null, monday_note: null }) ?? "";
    expect(n.replace(MONDAY_INTRO(1), "").match(/\d/)).toBeNull();
  });
});

describe("noteLines", () => {
  it("splits a note into one sentence per line", () => {
    expect(noteLines("One. Two sentences here. Three?")).toEqual(["One.", "Two sentences here.", "Three?"]);
  });
});
