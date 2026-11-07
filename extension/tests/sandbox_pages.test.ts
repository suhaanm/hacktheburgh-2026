import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import { installCapture } from "../src/content/capture";
import { roleOf } from "../src/shared/dom";
import type { CaptureRecord } from "../src/shared/types";
import { fire, matcher, SALT, validateAgainstEventSchema, zonerFor } from "./helpers";
import { makeEvent } from "../src/shared/events";

const dir = join(dirname(fileURLToPath(import.meta.url)), "fixtures", "sandbox");
const win = window as unknown as Window & typeof globalThis;
const HOST = { a: "127.0.0.1:7801", b: "127.0.0.1:7802", c: "127.0.0.1:7803" } as const;

function load(name: string): void {
  const html = readFileSync(join(dir, `${name}.html`), "utf8");
  const doc = new DOMParser().parseFromString(html, "text/html");
  document.documentElement.innerHTML = doc.documentElement.innerHTML;
}
const q = (s: string) => document.querySelector(s) as HTMLElement;

describe.each(["v1", "v2"] as const)("zones against the real sandbox markup (%s)", (layout) => {
  it("site a: wizard pages, result page, cliff button and panel", () => {
    const z = zonerFor(HOST.a);
    load(`a-step1-${layout}`);
    expect(z.forNav(document)).toBe("calc_site");               // first page of a calculator visit: OPEN_CALCULATOR
    expect(z.forScroll(document)).toBe("household_form");
    const field = q("select, input:not([type=hidden])");
    expect(z.forElement(field, roleOf(field))).toBe("household_form");
    load(`a-step2-${layout}`);
    expect(z.forNav(document)).toBe("household_form");          // later wizard pages are not another OPEN_CALCULATOR
    load(`a-result-${layout}`);
    expect(z.forNav(document)).toBe("calc_result");
    expect(z.forScroll(document)).toBe("calc_result");
    expect(z.forElement(q("#cliff-btn"), "button")).toBe("cliff_button");
    expect(z.forElement(q("#cliff-panel"), "region")).toBe("cliff_panel");
    const amount = q(layout === "v1" ? "#result-amount" : "#calc-total");
    expect(z.forElement(amount, "generic")).toBe("calc_result");
  });

  it("site b: one page, result page with the cliff block", () => {
    const z = zonerFor(HOST.b);
    load(`b-form-${layout}`);
    expect(z.forNav(document)).toBe("calc_site");
    expect(z.forScroll(document)).toBe("household_form");
    const field = q("input:not([type=hidden]), select");
    expect(z.forElement(field, roleOf(field))).toBe("household_form");
    load(`b-result-${layout}`);
    expect(z.forNav(document)).toBe("calc_result");
    expect(z.forElement(q("table td"), "cell")).toBe("calc_result");
    expect(z.forElement(q("#cliff-btn"), "button")).toBe("cliff_button");
  });

  it("site c: two-tab form and result page", () => {
    const z = zonerFor(HOST.c);
    load(`c-form-${layout}`);
    expect(z.forNav(document)).toBe("calc_site");
    const field = q("input:not([type=hidden]), select");
    expect(z.forElement(field, roleOf(field))).toBe("household_form");
    load(`c-result-${layout}`);
    expect(z.forNav(document)).toBe("calc_result");
    expect(z.forElement(q("table td"), "cell")).toBe("calc_result");
    expect(z.forElement(q("#cliff-btn"), "button")).toBe("cliff_button");
  });

  it("case note pages on site a's port: form and saved draft", () => {
    const z = zonerFor(HOST.a);
    load(`a-casenote-${layout}`);
    expect(z.forNav(document)).toBe("case_note");
    expect(z.forTab(document)).toBe("case_note");
    expect(z.forScroll(document)).toBe("case_note");
    const field = q("input, textarea, select");
    expect(z.forElement(field, roleOf(field))).toBe("case_note");
    load(`a-notedraft-${layout}`);
    expect(z.forNav(document)).toBe("case_note");
    expect(z.forTab(document)).toBe("case_note");
  });

  it("a calculator tab outside the case note is a results tab (RECONCILE when flipped)", () => {
    load(`b-result-${layout}`);
    expect(zonerFor(HOST.b).forTab(document)).toBe("results_tabs");
  });
});

describe("capture on the real result page", () => {
  let stop: (() => void) | null = null;
  afterEach(() => stop?.());

  it("click on the cliff button, copy of a result, paste into the note: zones and nothing else", () => {
    load("a-result-v1");
    const records: CaptureRecord[] = [];
    stop = installCapture({ win, salt: SALT, matcher, zoner: zonerFor(HOST.a), emit: (r) => void records.push(r), requireTrusted: false, isTop: true });
    q("#cliff-btn").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    const sel = window.getSelection()!;
    const r = document.createRange();
    r.selectNodeContents(q("#result-amount"));
    sel.removeAllRanges(); sel.addRange(r);
    fire(document, new Event("copy", { bubbles: true }));
    const types = records.map((x) => `${x.type}:${x.meta?.zone}`);
    expect(types).toContain("click:cliff_button");
    expect(types).toContain("copy:calc_result");
    const blob = JSON.stringify(records);
    expect(blob).not.toMatch(/£|GOV-|Check cliff|Estimated/);   // no result text, amounts or labels
    for (const rec of records) {
      const ev = makeEvent(rec, { person: "p_9f3a", role: "benefits-processor" }, { now: () => 1_700_000_000_000, uuid: () => "6f1d2b9a-0c47-4a38-9a51-2d1b7e8f5c01" });
      expect(validateAgainstEventSchema(ev)).toBe(true);
    }
  });

  it("the case note form records paste in zone case_note and no field value", () => {
    load("a-casenote-v1");
    const records: CaptureRecord[] = [];
    stop = installCapture({ win, salt: SALT, matcher, zoner: zonerFor(HOST.a), emit: (r) => void records.push(r), requireTrusted: false, isTop: true });
    const note = q("#note-text") as HTMLTextAreaElement;
    note.value = "PRIVATE NOTE TEXT";
    fire(note, new Event("paste", { bubbles: true }));
    expect(records.find((r) => r.type === "paste")?.meta?.zone).toBe("case_note");
    expect(JSON.stringify(records)).not.toContain("PRIVATE");
  });

  it("the household fields are captured; only the health question is skipped, on purpose", () => {
    // The pack's sensitive list flags "health condition" (special-category data), and each calculator's
    // limited-capability question asks about one. It is never captured at L0 and never recorded at L1.
    const HEALTH = new Set(["limited_capability", "health_limit", "health", "health-limits", "x-health-limits", "f_health", "x-health-limits", "health_limit"]);
    for (const name of ["a-step1-v1", "a-step1-v2", "a-step2-v1", "b-form-v1", "b-form-v2", "c-form-v1", "c-form-v2", "a-casenote-v1", "a-casenote-v2"]) {
      load(name);
      const controls = Array.from(document.querySelectorAll("input:not([type=hidden]), select, textarea, button"));
      expect(controls.length, name).toBeGreaterThan(2);
      const flagged = controls.filter((c) => matcher.inSensitiveContext(c)).map((c) => c.id || c.getAttribute("name") || c.getAttribute("data-testid") || "");
      const unexpected = flagged.filter((f) => !HEALTH.has(f));
      expect(unexpected, `${name} would lose these controls to the sensitive list`).toEqual([]);
      expect(flagged.length, name).toBeLessThanOrEqual(1);
    }
  });
});
