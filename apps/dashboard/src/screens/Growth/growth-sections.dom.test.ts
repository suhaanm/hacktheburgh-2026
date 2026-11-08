// @vitest-environment jsdom
// Growth is the one worker page for personal insight: My progress, Where my time goes, My steps, How my routines connect and, for programmers, My commits.
// Rendered on the built-in example data (the engine is unreachable), every section is a quiet title, ONE headline sentence and its numbers behind a closed
// disclosure, and the whole text, including what is closed, holds nothing a worker must not see (docs/knack-ux/views.md): no other person's id, no count of
// people, no average over others, no firm or team figure, no "ledger", no model name or cost.
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setState } from "../../store";
import Growth, { handlesSections } from "./index";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  vi.stubGlobal("fetch", () => Promise.reject(new Error("offline")));
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({ width: 900, height: 600, top: 0, left: 0, right: 900, bottom: 600, x: 0, y: 0, toJSON: () => ({}) });
  Element.prototype.scrollIntoView = () => undefined;
  window.location.hash = "#/growth";
  setState({ role: null, person: null, mock: true, extReady: true });
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

async function mount() {
  await act(async () => { root.render(createElement(Growth)); });
  // the sections load their own data one after the other; give each a turn
  for (let i = 0; i < 24; i++) await act(async () => { await new Promise((r) => setTimeout(r, 25)); });
}
/** The text around the first match of a rule, or null: a failing test then shows the offending words. */
const hit = (text: string, re: RegExp): string | null => {
  const g = new RegExp(re.source, re.flags.includes("g") ? re.flags : `${re.flags}g`);
  for (const m of text.matchAll(g)) {
    // the size of a meeting on the worker's own calendar ("Meeting, 5 to 9 people") is their own data, not a count of colleagues
    if (/people/i.test(m[0]) && /meeting|call|workshop|session/i.test(text.slice(Math.max(0, m.index! - 40), m.index!))) continue;
    return text.slice(Math.max(0, m.index! - 70), m.index! + m[0].length + 70);
  }
  return null;
};
const all = (): string => { host.querySelectorAll("details").forEach((d) => { d.open = true; }); return (host.textContent ?? "").replace(/\s+/g, " "); };

/** The firm rules of the view audit (scripts/lib/view-rules.mjs), as the worker-facing words a screen must never hold. */
const FIRM: [string, RegExp][] = [
  ["person id", /\bp_(?:[a-z]+_)*[a-z]*\d[a-z0-9_]*\b/i],
  ["person label", /\b(?:BP|DA|PR|PG)-\d{2}\b/],
  ["average over others", /\b(?:average|mean|median|typical)\s+(?:over|across|of|for)\s+(?:all|everyone|the\s+firm|your\s+colleagues|colleagues|the\s+team|other\s+(?:workers|learners|people))\b/i],
  ["the firm", /\bfirm[- ]?wide\b|\bwhole\s+firm\b|\bthe\s+firm\b|\bacross\s+(?:the|your)\s+(?:firm|team|company)\b/i],
  ["colleagues", /\bcolleagues?\b|\bco-?workers?\b|\bteammates?\b/i],
  ["a count of people", /\b\d[\d,]*\s+(?:people|persons|colleagues|workers|learners|users|staff|employees|juniors|experts|members)\b/i],
  ["other people", /\b(?:other|all|most|many)\s+(?:learners|workers|people|juniors|novices|users)\b|\beveryone\s+else\b/i],
  ["a ranking", /\b(?:percentile|leaderboard)\b|\b(?:top|bottom)\s+\d+\s?%|\bbetter\s+than\s+\d+\s?%/i],
];
const INTERNALS: [string, RegExp][] = [
  ["ledger", /\bledger\b/i],
  ["model name", /\b(?:gemini[\w.-]*|gpt[- ]?[\w.]+|openai|anthropic|claude|sonnet|haiku|opus)\b/i],
  ["cost", /(?:US\$|\$)\s?\d|\bper\s+(?:million\s+)?tokens?\b/i],
  ["hash", /\b[0-9a-f]{12,64}\b/i],
];

describe("Growth, the one worker page", () => {
  it("tells the host that it draws the sections itself", () => {
    expect(handlesSections).toBe(true);
  });

  it("has My progress, Where my time goes, My steps and How my routines connect, each with one headline sentence and a closed disclosure", async () => {
    await mount();
    for (const id of ["time", "steps", "map"]) {
      const sec = host.querySelector(`#gr-${id}`);
      expect(sec, `section ${id}`).not.toBeNull();
      const head = sec!.querySelector("h2.gr-sec__headline")!;
      expect(head.textContent!.trim().length, `headline of ${id}`).toBeGreaterThan(15);
      expect(head.textContent).not.toMatch(/\b(NaN|undefined|null|Infinity)\b/);
      const d = sec!.querySelector(":scope > details") as HTMLDetailsElement | null;
      expect(d, `disclosure of ${id}`).not.toBeNull();
      expect(d!.open).toBe(false);
    }
    expect(host.querySelector("h1")).not.toBeNull();
  });

  it("holds exactly one origin pill for the page, whatever the sections show", async () => {
    await mount();
    const pills = [...host.querySelectorAll(".page__aside .pill, .screenhead .pill")];
    expect(pills.length).toBe(1);
  });

  it("draws nothing a worker must not see, closed disclosures included", async () => {
    await mount();
    const text = all();
    // the explanation of the worker's case is part of the page text, so the rules below read it too
    expect(text).toMatch(/Explain this case/);
    expect(host.querySelector("#explain")).not.toBeNull();
    expect(host.querySelector("[data-testid=explain-footer]"), "the explanation ran on the example data").not.toBeNull();
    for (const [name, re] of [...FIRM, ...INTERNALS]) { const h = hit(text, re); expect(h === null, `${name}: ${h}`).toBe(true); }
  });

  it("My commits is for programmers: absent for a benefits processor, present for a programmer", async () => {
    await mount();
    expect(host.querySelector("#gr-commits")).toBeNull();
    act(() => root.unmount());
    root = createRoot(host);
    setState({ role: "programmer" });
    await mount();
    const sec = host.querySelector("#gr-commits");
    expect(sec).not.toBeNull();
    expect(sec!.querySelector("h2")!.textContent).toMatch(/commit habit/);
    const text = all();
    for (const [name, re] of [...FIRM, ...INTERNALS]) { const h = hit(text, re); expect(h === null, `commits ${name}: ${h}`).toBe(true); }
    expect(text).not.toMatch(/\bexperts\b/i);
  });

  it("opens the section the address names", async () => {
    window.location.hash = "#/growth?section=steps";
    await mount();
    expect((host.querySelector("#gr-steps > details") as HTMLDetailsElement).open).toBe(true);
    expect((host.querySelector("#gr-time > details") as HTMLDetailsElement).open).toBe(false);
  });
});
