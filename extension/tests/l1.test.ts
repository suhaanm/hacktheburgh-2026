import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cssEscape, installL1, locate, slotName, templatePath } from "../src/content/l1";
import type { RecordedStep } from "../src/shared/types";
import { ajvFor, fire, matcher, setPage } from "./helpers";

const validateBatch = ajvFor("recording.schema.json");
const win = window as unknown as Window & typeof globalThis;
const q = (s: string) => document.querySelector(s) as HTMLElement;
let stop: (() => void) | null = null;
let active = true;
let t = 0;

function start() {
  const steps: RecordedStep[] = [];
  let skipped = 0;
  stop = installL1({ win, matcher, emit: (s) => void steps.push(s), active: () => active, onSkipped: () => void skipped++, now: () => (t += 1000), requireTrusted: false, isTop: true });
  return { steps, skipped: () => skipped };
}
const batch = (steps: RecordedStep[]) => ({ schema: 1, routine_id: "calc-entry-3x", recording_id: "rec_0a1b2c3d4e5f", role: "benefits-processor", person: "p_9f3a", steps });

beforeEach(() => { active = true; t = 0; });
afterEach(() => { stop?.(); stop = null; });

describe("L1 recorder", () => {
  it("records selectors and parameter slots, never values", () => {
    setPage('<form action="/step/1"><select name="adults" id="adults"><option>1</option></select><input name="your_age" type="number" value="34"><textarea id="note">Dear PRIVATE</textarea><button id="continue">Continue</button></form>');
    const { steps } = start();
    (q("[name=your_age]") as HTMLInputElement).value = "34";
    fire(q("#adults"), new Event("change", { bubbles: true }));
    fire(q("[name=your_age]"), new Event("change", { bubbles: true }));
    fire(q("#note"), new Event("change", { bubbles: true }));
    fire(q("#continue"), new MouseEvent("click", { bubbles: true }));
    expect(steps.map((s) => s.op)).toEqual(["goto", "select", "fill", "fill", "click"]);
    expect(steps[1]).toMatchObject({ op: "select", selector: "#adults", param: "adults" });
    expect(steps[2]).toMatchObject({ op: "fill", selector: "input[name=\"your_age\"]", param: "your_age", input_type: "number" });
    expect(steps[4]).toMatchObject({ op: "click", selector: "#continue" });
    expect(JSON.stringify(steps)).not.toMatch(/34|PRIVATE/);
    expect(validateBatch(batch(steps)), JSON.stringify(validateBatch.errors)).toBe(true);
  });

  it("skips sensitive fields and login forms entirely and counts them", () => {
    setPage('<form><input name="username" id="u"><input type="password" id="p"><button id="go">Go</button></form><form><input name="ni_number" id="ni"></form>');
    const r = start();
    for (const id of ["u", "p", "ni"]) fire(q("#" + id), new Event("change", { bubbles: true }));
    fire(q("#go"), new MouseEvent("click", { bubbles: true }));
    expect(r.steps.filter((s) => s.op !== "goto")).toHaveLength(0);
    expect(r.skipped()).toBe(4);
  });

  it("records nothing while no routine is opted in", () => {
    setPage('<button id="b">go</button>');
    active = false;
    const { steps } = start();
    fire(q("#b"), new MouseEvent("click", { bubbles: true }));
    expect(steps).toHaveLength(0);
  });

  it("records a checkbox as the click, not as a value", () => {
    setPage('<input type="checkbox" id="c" name="agree">');
    const { steps } = start();
    fire(q("#c"), new MouseEvent("click", { bubbles: true }));
    fire(q("#c"), new Event("change", { bubbles: true }));
    expect(steps.filter((s) => s.op !== "goto")).toHaveLength(1);
    expect(steps[1]).toMatchObject({ op: "click", selector: "#c" });
  });

  it("records the goto with origin and templated path, no query or hash", () => {
    expect(templatePath("/casenote/CN-2041")).toBe("/casenote/_id_");
    expect(templatePath("/a/12345/b")).toBe("/a/_id_/b");
    expect(templatePath("/step/1")).toBe("/step/1");
    expect(templatePath("/x/123e4567-e89b-12d3-a456-426614174000")).toBe("/x/_id_");
    expect(templatePath("/we ird/ü")).toBe("/we_ird/_");
    setPage("<p>x</p>");
    const { steps } = start();
    expect(steps[0]!.op).toBe("goto");
    expect(steps[0]!.url).toMatch(/^http:\/\/localhost:3000\//);
    expect(steps[0]!.url).not.toMatch(/[?#]/);
  });

  it("falls back to role+name, then to a positional selector", () => {
    setPage('<button>Save draft</button><div><span><i></i></span></div>');
    expect(locate(q("button"))).toEqual({ role: "button", name: "Save draft" });
    const pos = locate(q("i")) as { selector: string };
    expect(pos.selector).toContain("i");
    expect(pos.selector.length).toBeLessThanOrEqual(300);
  });

  it("escapes ids and dedupes slot names", () => {
    expect(cssEscape("1a b")).toBe("\\31 a\\ b");
    const used = new Set<string>();
    expect([slotName("Your Age", used), slotName("your age", used), slotName("123", used), slotName("", used)]).toEqual(["your_age", "your_age_2", "p_123", "field"]);
  });

  it("every recorded step validates against the recording schema", () => {
    setPage('<form action="/step/1"><select id="a" name="adults"></select><input id="b" name="partner_age"><button id="c">Continue</button><a href="/x" id="l">Start again</a></form>');
    const { steps } = start();
    fire(q("#a"), new Event("change", { bubbles: true }));
    fire(q("#b"), new Event("change", { bubbles: true }));
    fire(q("#c"), new MouseEvent("click", { bubbles: true }));
    fire(q("#l"), new MouseEvent("click", { bubbles: true, cancelable: true }));
    expect(validateBatch(batch(steps)), JSON.stringify(validateBatch.errors)).toBe(true);
  });
});
