// @vitest-environment jsdom
// The Genome transition graph in a real DOM: the same rules as the work graph. Two canvases (expert, novice), no text drawn, an icon per step, a name only on hover,
// focus or a click, one tab stop each, the moves the novice misses named for a screen reader, and a key made of pictures.
import { createElement, act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import fx from "../../fixtures/transitions.json";
import { stepKind } from "../../lib/nodeIcons";
import type { Transitions } from "../../types";
import { TransitionGraph, transitionLegend } from "../TransitionGraph";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const tr = (fx as unknown as { data: Transitions }).data;
let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({ width: 900, height: 600, top: 0, left: 0, right: 900, bottom: 600, x: 0, y: 0, toJSON: () => ({}) });
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

const mount = (data: Transitions = tr) => { act(() => { root.render(createElement(TransitionGraph, { data })); }); };
const svgs = () => [...host.querySelectorAll<SVGSVGElement>("svg.tgraph__svg")];
const key = (el: Element, k: string) => act(() => { el.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true })); });
const enter = (el: Element) => act(() => { el.dispatchEvent(new MouseEvent("pointerover", { bubbles: true, relatedTarget: null })); });
const leave = (el: Element) => act(() => { el.dispatchEvent(new MouseEvent("pointerout", { bubbles: true, relatedTarget: document.body })); });
const tip = () => host.querySelector<HTMLElement>(".gtip");

describe("transition graph", () => {
  it("draws an expert canvas and a novice canvas with a step each, and writes no text on either", () => {
    mount();
    expect(svgs()).toHaveLength(2);
    for (const s of svgs()) {
      expect(s.querySelectorAll(".tgnode")).toHaveLength(tr.nodes.length);
      expect(s.querySelectorAll("text, title, tspan").length).toBe(0);
      expect((s.textContent ?? "").trim()).toBe("");
      expect(s.querySelectorAll(".tgnode .gglyph")).toHaveLength(tr.nodes.length);
    }
  });
  it("is one tab stop per canvas, with an accessible name on every step", () => {
    mount();
    for (const s of svgs()) {
      expect(s.getAttribute("tabindex")).toBe("0");
      expect(s.getAttribute("role")).toBe("listbox");
      expect(s.querySelectorAll("[tabindex], a, button").length).toBe(0);
      for (const n of s.querySelectorAll(".tgnode")) expect(n.getAttribute("aria-label")).toMatch(/^[A-Z][a-z ]+\. (\d+ seconds here|Not done here)\./);
    }
  });
  it("tells a step the novice never does apart: a dashed muted ring, and 'Not done here' in its name", () => {
    mount();
    const [expert, novice] = svgs();
    const absentNovice = [...novice.querySelectorAll(".tgnode")].filter((n) => n.getAttribute("data-tone") === "muted");
    expect(absentNovice.length).toBe(tr.nodes.filter((n) => n.novice_dwell_s <= 0).length);
    for (const n of absentNovice) expect(n.getAttribute("aria-label")).toContain("Not done here");
    expect([...expert.querySelectorAll(".tgnode")].filter((n) => n.getAttribute("data-tone") === "muted").length).toBe(tr.nodes.filter((n) => n.expert_dwell_s <= 0).length);
  });
  it("names the moves the novice misses, in the name of the step they start from, and counts them on the canvas", () => {
    mount();
    const novice = svgs()[1];
    expect(novice.getAttribute("aria-label")).toMatch(/\d+ moves the expert makes that this person makes rarely or never/);
    const all = [...novice.querySelectorAll(".tgnode")].map((n) => n.getAttribute("aria-label")!).join(" ");
    expect(all).toMatch(/Missing moves? to /);
    expect(novice.querySelectorAll(".tg-edge--missing").length).toBeGreaterThan(0);
    expect(svgs()[0].querySelectorAll(".tg-edge--missing").length).toBe(0);
  });
  it("opens a card on hover with the step, what it is and the time, and closes it on leave", () => {
    mount();
    const first = svgs()[0].querySelector(".tgnode")!;
    expect(tip()).toBeNull();
    enter(first);
    expect(tip()).not.toBeNull();
    expect(tip()!.textContent).toMatch(/Read/);
    expect(tip()!.textContent).toMatch(/s here/);
    leave(first);
    expect(tip()).toBeNull();
  });
  it("names a missing move when the pointer is on its line", () => {
    mount();
    const hits = [...svgs()[1].querySelectorAll(".tg-edge--hit")];
    expect(hits.length).toBeGreaterThan(0);
    const missing = [...svgs()[1].querySelectorAll("g")].find((g) => g.querySelector(".tg-edge--missing"))!;
    enter(missing.querySelector(".tg-edge--hit")!);
    expect(tip()!.textContent).toMatch(/Missing|Less often/);
    expect(tip()!.textContent).toMatch(/ to /);
  });
  it("arrow keys move between steps, Enter keeps a name open, Escape closes it", () => {
    mount();
    const svg = svgs()[0];
    act(() => { svg.focus(); });
    const first = svg.getAttribute("aria-activedescendant");
    expect(first).toMatch(/^tg-expert-/);
    expect(tip()).not.toBeNull();
    key(svg, "ArrowDown");
    expect(svg.getAttribute("aria-activedescendant")).not.toBe(first);
    key(svg, "Enter");
    expect(tip()!.hasAttribute("data-pinned")).toBe(true);
    act(() => { svg.blur(); });
    expect(tip()).not.toBeNull();
    key(svg, "Escape");
    expect(tip()).toBeNull();
  });
  it("copes with one step and with a self-loop and an edge to nothing", () => {
    mount({ nodes: [{ id: "a", cog: "READ", expert_dwell_s: 5, novice_dwell_s: 6 }], edges: [{ from: "a", to: "a", expert_freq: 0.5, novice_freq: 0.5, missing_for_novice: false, planted: null }, { from: "a", to: "ghost", expert_freq: 1, novice_freq: 1, missing_for_novice: false, planted: null }] });
    expect(svgs()).toHaveLength(2);
    expect(host.innerHTML).not.toContain("NaN");
    expect(svgs()[0].querySelectorAll(".tgnode")).toHaveLength(1);
  });
  it("has a key of pictures behind What are these?, one for each kind of step in the flow and each mark", () => {
    mount();
    const d = host.querySelector("details")!;
    expect(d.querySelector("summary")!.textContent).toBe("What are these?");
    const entries = transitionLegend(tr);
    expect(host.querySelectorAll(".gkey__item")).toHaveLength(entries.length);
    expect(entries.filter((e) => e.group === "kind").map((e) => e.id).sort()).toEqual([...new Set(tr.nodes.map((n) => `step-${stepKind(n.cog)}`))].sort());
    for (const b of host.querySelectorAll(".gkey__item")) expect((b.textContent ?? "").trim()).toBe("");
    expect(entries.map((e) => e.name)).toEqual(expect.arrayContaining(["Size", "Thickness", "Missing move", "Detour", "Not done here"]));
  });
});
