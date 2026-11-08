import { describe, expect, it } from "vitest";
import report from "../fixtures/eval-report.json";
import { agenticRounds, barWords, halfFigure, providerName, roundLabel } from "./agenticRounds";

const agentic = (report as unknown as { sections: Record<string, unknown> }).sections.agentic;

describe("agenticRounds", () => {
  const r = agenticRounds(agentic);
  it("reads the two held-out rounds of the report, oldest first, never pooled", () => {
    expect(r).not.toBeNull();
    expect(r!.rounds.map((x) => x.id)).toEqual(["round1", "round2"]);
    expect(r!.rounds.map((x) => x.provider)).toEqual(["OpenAI", "Gemini"]);
    expect(r!.rounds.map((x) => x.label)).toEqual(["Round 1", "Round 2"]);
  });
  it("gives each half its own k of n and interval", () => {
    const [one, two] = r!.rounds;
    expect(one.clean).toMatchObject({ k: 1, n: 4 });
    expect(one.injected).toMatchObject({ k: 20, n: 20 });
    expect(two.clean).toMatchObject({ k: 18, n: 20, barMet: false });
    expect(two.injected).toMatchObject({ k: 20, n: 20 });
    expect(halfFigure(two.clean!)).toBe("18 of 20 (70 to 97%)");
  });
  it("opens with the newest round and says what the bar did", () => {
    expect(r!.headline).toContain("18 of 20");
    expect(r!.headline).toContain("the pre-registered bar was not met");
    expect(r!.headline).toContain("not pooled");
    expect(r!.barLower).toBeCloseTo(0.8);
  });
  it("says why a bar was not tested, and never calls an untested bar met", () => {
    expect(barWords(r!.rounds[0].clean)).toMatch(/not tested.*n = 4/);
    expect(barWords(r!.rounds[1].clean)).toBe("not met");
    expect(barWords(null)).toBe("not run");
  });
  it("checks the gate against the build frozen for the round", () => {
    expect(r!.rounds.every((x) => x.gateOk === true)).toBe(true);
    expect(r!.rounds[0].gateVersion).not.toBe(r!.rounds[1].gateVersion);
  });
  it("is null when the section is missing, empty or not an object, and never throws on bad numbers", () => {
    expect(agenticRounds(null)).toBeNull();
    expect(agenticRounds({})).toBeNull();
    expect(agenticRounds({ heldout: { clean: { round: "round1", passed_code_check: { k: "x", n: NaN } } } })).toBeNull();
    const odd = agenticRounds({ heldout: { clean: { round: "round3", provider: "acme", passed_code_check: { k: 3, n: 4 } } } });
    expect(odd?.rounds[0].provider).toBe("Acme");
    expect(odd?.headline).toContain("3 of 4");
  });
  it("names providers and rounds in words", () => {
    expect(providerName("openai")).toBe("OpenAI");
    expect(providerName(null)).toBe("Unknown provider");
    expect(roundLabel("round2")).toBe("Round 2");
    expect(roundLabel("pilot_a")).toBe("pilot a");
  });
});
