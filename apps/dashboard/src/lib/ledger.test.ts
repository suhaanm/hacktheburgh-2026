import { describe, expect, it } from "vitest";
import type { LedgerEntry } from "../types";
import { blockReasonLabel, callsToday, countLines, filterLedger, fmtBytes, imageSize, rowClass, sentRows, sourceLabel } from "./ledger";

const row = (o: Partial<LedgerEntry>): LedgerEntry => ({ t: "2026-11-07T10:00:00Z", purpose: "glance.frame", schema: null, fields: [], payload: null, model: null, bytes: 0, ...o });
const entries: LedgerEntry[] = [
  row({ purpose: "briefing_wording", payload: { a: 1 }, fields: ["a"], model: "m", bytes: 10 }),
  row({ kind: "image", status: "ok", source: "sandbox", image: { kind: "glance", bytes: 2048, width: 640, height: 400 } }),
  row({ kind: "image", status: "ok", source: "real_screen", image: { kind: "point", bytes: 1024 } }),
  row({ kind: "image", status: "blocked", reason: "unattended", source: "real_screen" }),
  row({ kind: "image", status: "blocked", reason: "secure_input", source: "real_screen" }),
];

describe("ledger rows", () => {
  it("tells text rows from image rows and blocked image rows", () => {
    expect(entries.map(rowClass)).toEqual(["text", "image", "image", "image_blocked", "image_blocked"]);
  });
  it("filters by kind, keeping blocked rows apart from sent ones", () => {
    expect(filterLedger(entries, "all")).toHaveLength(5);
    expect(filterLedger(entries, "text")).toHaveLength(1);
    expect(filterLedger(entries, "images")).toHaveLength(4);
    expect(filterLedger(entries, "blocked")).toHaveLength(2);
  });
  it("does not count a blocked row as a call", () => {
    expect(sentRows(entries)).toHaveLength(3);
    const today = callsToday(entries, new Date("2026-11-07T12:00:00Z"));
    expect(Object.values(today).reduce((a, b) => a + b, 0)).toBe(3);
  });
  it("gives each block reason in plain words and keeps unknown ones readable", () => {
    expect(blockReasonLabel("unattended")).toMatch(/background run may never/);
    expect(blockReasonLabel("no_consent")).toMatch(/opted in/);
    expect(blockReasonLabel("secure_input")).toMatch(/secure field/);
    expect(blockReasonLabel("denylisted_app")).toMatch(/keep private/);
    expect(blockReasonLabel("new_reason")).toBe("new reason");
    expect(blockReasonLabel(null)).toMatch(/refused/);
  });
  it("labels sources and sorts counts, largest first", () => {
    expect(sourceLabel("real_screen")).toBe("Your real screen");
    expect(sourceLabel("sandbox")).toBe("A sandbox site");
    expect(countLines({ a: 1, b: 3, c: 3 }, (k) => k.toUpperCase()).map((x) => x.label)).toEqual(["B", "C", "A"]);
    expect(countLines(undefined, (k) => k)).toEqual([]);
  });
  it("prints sizes safely, including the null a local model reports before its file is checked", () => {
    expect(fmtBytes(null)).toBe("size not known");
    expect(fmtBytes(undefined)).toBe("size not known");
    expect(fmtBytes(512)).toBe("512 B");
    expect(fmtBytes(2048)).toBe("2.0 KB");
    expect(imageSize(entries[1])).toBe("640 × 400 px");
    expect(imageSize(entries[2])).toBe("size not recorded");
  });
  it("never lets a picture or text field into an image row of the fixture", () => {
    for (const e of entries.filter((x) => x.kind === "image")) {
      expect(e.payload).toBeNull();
      expect(e.fields).toEqual([]);
      for (const v of Object.values(e.image ?? {})) expect(typeof v === "number" || /^[a-z0-9_]+$/.test(String(v))).toBe(true);
    }
  });
});
