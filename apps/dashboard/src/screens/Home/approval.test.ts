import { describe, expect, it } from "vitest";
import type { QueueItem } from "../../types";
import { approvalLabels, consequence, leadAndRest, plainWords } from "../NeedsYou/model";
import { blockingItem, finalizeOf, isSafetyPause, remainingAfter } from "./approval";

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
  it("ignores decided and expired items, and is null for an empty, missing or null list", () => {
    expect(blockingItem([item("a", "irreversible_step", "irreversible", undefined, "approved")])).toBeNull();
    expect(blockingItem([item("a", "irreversible_step", "irreversible", undefined, "expired")])).toBeNull();
    expect(blockingItem([])).toBeNull();
    expect(blockingItem(null)).toBeNull();
    expect(blockingItem(undefined)).toBeNull();
  });
  it("copes with a time it cannot read: that item goes last, and ties fall back to the id so the order never shuffles", () => {
    const bad = item("a", "irreversible_step", "irreversible", "not a time");
    const good = item("b", "irreversible_step", "irreversible", "2026-11-08T09:00:00Z");
    expect(blockingItem([bad, good])?.id).toBe("b");
    const same = [item("z", "outward_step", "outward"), item("m", "outward_step", "outward")];
    expect(blockingItem(same)?.id).toBe("m");
    expect(blockingItem([...same].reverse())?.id).toBe("m");
  });
  it("copes with thousands of waiting items without taking more than one", () => {
    const many = Array.from({ length: 5000 }, (_, i) => item(`x${i}`, "outward_step", "outward", `2026-11-0${1 + (i % 7)}T09:00:00Z`));
    expect(blockingItem(many)?.created_at.startsWith("2026-11-01")).toBe(true);
  });
  it("recognises a safety pause, the one blocking kind that never gets a primary button", () => {
    expect(isSafetyPause({ kind: "injection_pause" })).toBe(true);
    expect(isSafetyPause({ kind: "irreversible_step" })).toBe(false);
  });
  it("uses Needs you's own words: the consequence, the labels and the plain wording", () => {
    expect(consequence("irreversible")).toBe("Cannot be undone.");
    expect(consequence("outward")).toBe("Reaches outside.");
    expect(consequence("normal")).toBeNull();
    expect(approvalLabels("irreversible_step")).toEqual({ yes: "Approve and submit", no: "Reject" });
    expect(approvalLabels("injection_pause").yes).toBe("Resume the run");
    expect(plainWords("The routine dropped one rung to A1.")).toBe("The routine dropped one step to watching.");
    expect(leadAndRest("One. Two. Three.", 30)).toEqual({ lead: "One. Two. Three.", rest: "" });
  });
  it("reads what an approval did with the step it released, from either shape of answer", () => {
    expect(finalizeOf({ finalize: "failed" })).toBe("failed");
    expect(finalizeOf({ data: { finalize: "submitted" } })).toBe("submitted");
    expect(finalizeOf({ data: { finalize: "none" }, source: "live" })).toBe("none");
    expect(finalizeOf({ data: {} })).toBeNull();
    expect(finalizeOf({ finalize: "maybe" })).toBeNull();
    expect(finalizeOf(null)).toBeNull();
    expect(finalizeOf(undefined)).toBeNull();
    expect(finalizeOf("failed")).toBeNull();
  });
  it("leaves the rest for the needs-you row, never below zero", () => {
    expect(remainingAfter(3, true)).toBe(2);
    expect(remainingAfter(3, false)).toBe(3);
    expect(remainingAfter(0, true)).toBe(0);
    expect(remainingAfter(Number.NaN, true)).toBe(0);
  });
});
