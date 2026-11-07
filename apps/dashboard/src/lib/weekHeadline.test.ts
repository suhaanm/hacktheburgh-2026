import { describe, expect, it } from "vitest";
import { weekHeadline } from "./week";

const f = (m: number) => ({ meeting_h: m }) as never;

describe("weekHeadline names whose week it is", () => {
  it("says 'you' for the worker's own calendar, as before", () => {
    expect(weekHeadline(f(12.5), f(8))).toBe("You spend 12.5 hours a week in meetings, 4.5 more than the expert");
    expect(weekHeadline(f(8.2), f(8), null)).toBe("Your meeting load is about the same as the expert's, 8.2 hours a week");
  });
  it("names the person when another calendar is picked", () => {
    expect(weekHeadline(f(12.5), f(8), "BP-07")).toBe("BP-07 spends 12.5 hours a week in meetings, 4.5 more than the expert");
    expect(weekHeadline(f(6), f(8), "Marcus")).toBe("Marcus spends 6 hours a week in meetings, 2 fewer than the expert");
    expect(weekHeadline(f(8.1), f(8), "Marcus")).toBe("Marcus's meeting load is about the same as the expert's, 8.1 hours a week");
  });
  it("never says 'you' or 'your' for someone else", () => {
    expect(weekHeadline(f(12.5), f(8), "BP-07")).not.toMatch(/\byou(r)?\b/i);
    expect(weekHeadline({} as never, {} as never, "BP-07")).toBe("BP-07's week against the expert's");
    expect(weekHeadline({} as never, {} as never)).toBe("Your week against the expert's");
  });
});
