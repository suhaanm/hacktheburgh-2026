import { describe, expect, it } from "vitest";
import explainFx from "../fixtures/evidence-explain.json";
import packetFx from "../fixtures/evidence-packet.json";
import type { EvidencePacket, ExplainResult } from "../types";
import { actionsOf, askedTimeNote, badgeText, bodySentences, checkReading, cleanQuestion, CHIPS, fallbackReading, fmtFact, isAnswer, limitsOf, pathWords, sourceReading, usesWithFacts } from "./explain";

const dflt = (explainFx as unknown as { default: { data: ExplainResult } }).default.data;
const sure = (explainFx as unknown as { how_sure: { data: ExplainResult } }).how_sure.data;
const packet = (packetFx as unknown as { data: EvidencePacket }).data;

describe("explain: reading a result", () => {
  it("finds the words, the coaching and the limits", () => {
    expect(bodySentences(dflt).length).toBeGreaterThanOrEqual(3);
    expect(isAnswer(dflt)).toBe(false);
    expect(isAnswer(sure)).toBe(true);
    expect(actionsOf(dflt).length).toBeGreaterThan(0);
    expect(actionsOf(dflt)[0].chosen_by).toBe("code");
    expect(limitsOf(dflt).length).toBeGreaterThanOrEqual(3);
    expect(limitsOf(dflt).map((l) => l.id)).toContain("synthetic_data");
  });
  it("says where the words came from and never claims they are true", () => {
    expect(sourceReading({ source: "template", model: null }).label).toMatch(/template/);
    expect(sourceReading({ source: "local", model: "m" }).label).toMatch(/this laptop/);
    expect(sourceReading({ source: "cloud", model: "m" }).detail).toMatch(/privacy guard/);
    const c = checkReading(dflt.check);
    expect(c.ok).toBe(true);
    expect(c.text).toMatch(/15 numbers/);
    expect(c.text).toMatch(/not that the data is right/);
    expect(checkReading({ ok: false }).ok).toBe(false);
    expect(checkReading({ ok: false }).text).toMatch(/do not rely/);
  });
  it("prints the badge from the answer's own n and unit", () => {
    expect(badgeText(dflt.badge)).toBe("n = 24 people");
    expect(badgeText({ origin: "synthetic", n: 1, n_unit: "people", split: null })).toBe("n = 1 person");
    expect(badgeText({ origin: "synthetic", n: 4, n_unit: "episodes", split: null })).toBe("n = 4 episodes");
  });
  it("says so when a model's words were turned away, and stays quiet when the template was the plan", () => {
    expect(fallbackReading(dflt)).toBeNull();
    const rejected = { source: "template" as const, fallback_reason: "provenance", attempts: [{ route: "local", ok: false, reason: "provenance", codes: ["number_not_in_packet"] }] };
    expect(fallbackReading(rejected)).toMatch(/fixed template because a number or name in the model's words did not match the data/);
    expect(fallbackReading({ ...rejected, fallback_reason: "schema" })).toMatch(/did not follow the required form/);
    expect(fallbackReading({ source: "template", fallback_reason: "weird_code", attempts: [] })).toMatch(/weird code/);
    expect(fallbackReading({ source: "local", fallback_reason: null, attempts: [] })).toBeNull();
  });
  it("quotes back only a time the worker typed, never the question", () => {
    expect(askedTimeNote({ asked_s: null, matches_case: null })).toBeNull();
    expect(askedTimeNote({ asked_s: 840, matches_case: false })).toMatch(/14 min.*does not match this case/);
    expect(askedTimeNote({ asked_s: 840, matches_case: true })).toMatch(/matches this case/);
  });
});

describe("explain: where a number comes from", () => {
  it("matches every path a sentence cites to a fact in the packet", () => {
    for (const s of bodySentences(dflt)) for (const u of usesWithFacts(s.uses, packet.facts)) expect(u.fact, `missing ${u.path}`).not.toBeNull();
    for (const a of actionsOf(dflt)) for (const u of usesWithFacts(a.uses, packet.facts)) expect(u.fact, `missing ${u.path}`).not.toBeNull();
  });
  it("keeps a path the packet does not hold, marked missing", () => {
    const u = usesWithFacts(["gap.case_s", "gap.not_there"], packet.facts);
    expect(u[0].fact).not.toBeNull();
    expect(u[1]).toEqual({ path: "gap.not_there", fact: null });
  });
  it("writes values for a person", () => {
    expect(fmtFact({ value: 585, unit: "s" })).toBe("9 min 45 s");
    expect(fmtFact({ value: 14.6, unit: "s" })).toBe("14.6 s");
    expect(fmtFact({ value: 0.103, unit: "share" })).toBe("10.3%");
    expect(fmtFact({ value: 291.89, unit: "gbp" })).toBe("£292");
    expect(fmtFact({ value: 24, unit: "count" })).toBe("24");
    expect(pathWords("habit.search_loops.seconds")).toBe("habit · search loops · seconds");
  });
});

describe("explain: the question", () => {
  it("offers five chips", () => {
    expect(CHIPS).toHaveLength(5);
    expect(CHIPS.map((c) => c.id)).toContain("how_sure");
  });
  it("cleans what is sent: control characters out, spaces collapsed, 400 characters at most, nothing becomes undefined", () => {
    expect(cleanQuestion("  why   was\tI \n slow?  ")).toBe("why was I slow?");
    expect(cleanQuestion("a\u0000b\u0007c")).toBe("abc");
    expect(cleanQuestion("x".repeat(500))?.length).toBe(400);
    expect(cleanQuestion("   ")).toBeUndefined();
    expect(cleanQuestion("")).toBeUndefined();
  });
  it("never uses the words improve or expert in the fixed copy it offers", () => {
    const copy = JSON.stringify(CHIPS) + sourceReading({ source: "template", model: null }).label + sourceReading({ source: "local", model: "m" }).detail + checkReading(dflt.check).text;
    expect(copy).not.toMatch(/improv|expert/i);
  });
});
