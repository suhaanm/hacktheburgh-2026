import { describe, expect, it } from "vitest";
import onboardingFx from "../fixtures/onboarding.json";
import type { OnboardingQuestions } from "../types";
import { buildPreview, daysText } from "./memoryPreview";

const roles = onboardingFx as unknown as Record<string, OnboardingQuestions>;
const answers = (q: OnboardingQuestions) => ({ tools: [q.questions[0].options[0].value], risky: q.questions[1].options.map((o) => o.value), tone: q.pack.tone_defaults.length, pace: "gradual", hours: { start: "09:00", end: "17:30", days: [0, 1, 2, 3, 4] } });

describe("onboarding preview", () => {
  it("gives visibly different files for different roles", () => {
    const a = buildPreview("benefits-processor", roles["benefits-processor"], answers(roles["benefits-processor"])).text;
    const b = buildPreview("data-analyst", roles["data-analyst"], answers(roles["data-analyst"])).text;
    expect(a).not.toEqual(b);
    expect(a).toMatch(/role: benefits-processor/);
    expect(b).toMatch(/role: data-analyst/);
    expect(a).toMatch(/submit/i);
    expect(b).toMatch(/drop|overwrite/i);
    expect(a).toMatch(/Summaries: short/);
    expect(b).toMatch(/Summaries: detailed/);
  });
  it("highlights only lines that came from the worker's answers", () => {
    const empty = buildPreview("programmer", roles.programmer, {});
    expect(empty.fresh.size).toBe(0);
    const some = buildPreview("programmer", roles.programmer, { tone: "detailed" });
    expect(some.fresh.size).toBe(1);
  });
  it("shows the capture line only when the worker said yes", () => {
    const q = roles.programmer;
    expect(buildPreview("programmer", q, { capture: true }).text).toContain("- Capture: times only");
    expect(buildPreview("programmer", q, { capture: false }).text).not.toMatch(/Capture/);
    expect(buildPreview("programmer", q, {}).text).not.toMatch(/Capture/);
  });
  it("describes days in plain words", () => {
    expect(daysText([0, 1, 2, 3, 4])).toBe("Mon to Fri");
    expect(daysText([0, 2, 3, 6])).toBe("Mon, Wed to Thu, Sun");
    expect(daysText([])).toBe("no fixed days");
  });
});
