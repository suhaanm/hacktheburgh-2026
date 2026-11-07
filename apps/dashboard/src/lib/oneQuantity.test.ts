import { describe, expect, it } from "vitest";
import { offenders, oneQuantity, quantitiesIn, sentencesOf } from "./oneQuantity";

describe("one quantity per sentence", () => {
  it("passes a count, a measure, a rate and a fraction", () => {
    for (const s of [
      "1 thing needs you",
      "3 things need you",
      "About 1 hour a week could run for you.",
      "On the cliff check you usually take about 35 seconds longer than the expert.",
      "On reconciling before the note you finished 17 of your last 20 cases without help.",
      "Seen 58 times in 3 weeks.",
      "Could save 4 to 7 hours.",
      "About 2.4 to 4.5 hours a week could run for you.",
      "One thing needs you.",
    ]) expect(quantitiesIn(s), s).toBe(1);
  });
  it("fails two separate quantities, the spec's own example first", () => {
    expect(oneQuantity("2 repeats could run for you, about 1 hour a week")).toBe(false);
    expect(quantitiesIn("2 repeats, about 1 hour a week")).toBe(2);
    expect(oneQuantity("You took 35 seconds longer on 4 cases")).toBe(false);
    expect(oneQuantity("Three things need you and 2 are urgent.")).toBe(false);
  });
  it("passes the spec's good rewrite", () => {
    expect(oneQuantity("About 1 hour a week could run for you.")).toBe(true);
  });
  it("does not count dates, times or ids", () => {
    for (const s of ["Week of 9 November", "Usual hours 09:00 to 17:30, Monday to Friday", "Submit case note CN-2041", "From 9 November to 15 November", "Run r_demo_3 finished", "Level A2 asks first"]) {
      expect(quantitiesIn(s), s).toBe(0);
    }
  });
  it("checks each sentence on its own", () => {
    expect(sentencesOf("Seen 58 times in 3 weeks. Could save 4 to 7 hours.")).toEqual(["Seen 58 times in 3 weeks.", "Could save 4 to 7 hours."]);
    expect(oneQuantity("Seen 58 times in 3 weeks. Could save 4 to 7 hours.")).toBe(true);
    expect(sentencesOf("It took 3.4 hours. Fine.")).toEqual(["It took 3.4 hours.", "Fine."]);
    expect(offenders("Fine. 2 repeats, about 1 hour a week.")).toEqual(["2 repeats, about 1 hour a week."]);
  });
  it("reads a number word as a quantity", () => {
    expect(quantitiesIn("Two things from your week")).toBe(1);
    expect(quantitiesIn("Nothing stands out this week.")).toBe(0);
  });
});
