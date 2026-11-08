import { describe, expect, it } from "vitest";
import { TABS, defaultTab, tabOf } from "./model";

describe("which tab Routines opens on (QA Q1-12)", () => {
  it("opens on Could automate when Your routines is empty and that list is not, with no tab asked for", () => {
    expect(defaultTab(null, 0, 2)).toBe("could-automate");
    expect(defaultTab(undefined, 0, 8)).toBe("could-automate");
  });
  it("opens on Your routines when it has something, or when nothing has", () => {
    expect(defaultTab(null, 2, 8)).toBe("running");
    expect(defaultTab(null, 1, 0)).toBe("running");
    expect(defaultTab(null, 0, 0)).toBe("running");
  });
  it("a tab asked for in the address always wins, so a worker who chose Your routines keeps it", () => {
    expect(defaultTab("running", 0, 5)).toBe("running");
    expect(defaultTab("could-automate", 4, 0)).toBe("could-automate");
    expect(defaultTab("nonsense", 0, 5)).toBe("running");
  });
  it("the tabs are called Your routines and Could automate, and the address word for the first is 'running'", () => {
    expect(TABS.map((t) => t.label)).toEqual(["Your routines", "Could automate"]);
    expect(tabOf("running")).toBe("running");
  });
});
