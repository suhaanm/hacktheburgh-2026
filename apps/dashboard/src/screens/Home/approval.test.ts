import { describe, expect, it } from "vitest";
import type { QueueItem } from "../../types";
import { blockingItem, consequence, decisionLabels, remainingAfter } from "./approval";

const item = (id: string, kind: QueueItem["kind"], risk: QueueItem["risk_class"] = "normal", at = "2026-11-08T09:00:00Z", status: QueueItem["status"] = "pending"): QueueItem => ({
  id, created_at: at, routine_id: null, run_id: `r_${id}`, kind, title: id, summary: "", risk_class: risk,
  evidence: { screenshots: [], extracted: {}, expected: {}, diff: [], tier_log: [] }, status, decided_at: null, decided_by: null,
});

describe("what takes Home's hero slot", () => {
  it("is an irreversible or outward approval, or a safety pause, and nothing else", () => {
    expect(blockingItem([item("a", "batch_result"), item("b", "shadow_mismatch")])).toBeNull();
    expect(blockingItem([item("a", "irreversible_step", "irreversible")])?.id).toBe("a");
    expect(blockingItem([item("a", "outward_step", "outward")])?.id).toBe("a");
    expect(blockingItem([item("a", "injection_pause")])?.id).toBe("a");
  });
  it("ranks a safety pause over an irreversible step over an outward one, oldest first within a kind", () => {
    const items = [item("o", "outward_step", "outward", "2026-11-08T08:00:00Z"), item("i2", "irreversible_step", "irreversible", "2026-11-08T10:00:00Z"), item("i1", "irreversible_step", "irreversible", "2026-11-08T09:00:00Z"), item("p", "injection_pause", "normal", "2026-11-08T11:00:00Z")];
    expect(blockingItem(items)?.id).toBe("p");
    expect(blockingItem(items.filter((x) => x.id !== "p"))?.id).toBe("i1");
    expect(blockingItem(items.filter((x) => x.kind === "outward_step"))?.id).toBe("o");
  });
  it("ignores decided items, and is null for an empty list", () => {
    expect(blockingItem([item("a", "irreversible_step", "irreversible", undefined, "approved")])).toBeNull();
    expect(blockingItem([])).toBeNull();
  });
  it("prints the consequence for every blocking kind", () => {
    expect(consequence({ kind: "irreversible_step", risk_class: "irreversible" })).toBe("Cannot be undone.");
    expect(consequence({ kind: "outward_step", risk_class: "outward" })).toBe("Reaches outside.");
    expect(consequence({ kind: "injection_pause", risk_class: "normal" })).toBe("Paused for safety.");
    expect(consequence({ kind: "batch_result", risk_class: "normal" })).toBeNull();
  });
  it("names the two buttons in at most three words each, except the spec's own two longer ones", () => {
    expect(decisionLabels("irreversible_step")).toEqual({ yes: "Approve and submit", no: "Reject" });
    expect(decisionLabels("outward_step")).toEqual({ yes: "Approve and send", no: "Reject" });
    expect(decisionLabels("injection_pause").yes).toBe("Resume the run");
  });
  it("leaves the rest for the needs-you row", () => {
    expect(remainingAfter(3, true)).toBe(2);
    expect(remainingAfter(3, false)).toBe(3);
    expect(remainingAfter(0, true)).toBe(0);
  });
});
