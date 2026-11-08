// @vitest-environment jsdom
// The graph layer in a real DOM: no text drawn on the canvas, a name only on hover, focus or a click, one tab stop, the arrow keys and Escape,
// an accessible name on every node, the edge cases (empty, one node, long and unicode and repeated labels, self-loops, a thousand nodes), and the key.
import { createElement, act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import workFx from "../../fixtures/workgraph.json";
import type { WorkGraph, WorkLink, WorkNode, WorkNodeType } from "../../types";
import { GraphCanvas } from "./GraphCanvas";
import { GraphLegend, WORK_LEGEND } from "./GraphLegend";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const wg = (workFx as unknown as { data: WorkGraph }).data;
const mk = (id: string, type: WorkNodeType = "routine", over: Partial<WorkNode> = {}): WorkNode => ({ id, type, label: id, size: 30, strength: 0.8, last_seen: "2026-11-07", why: "Seen often.", editable: true, memory_line_id: null, ...over });
const lk = (a: string, b: string, kind: "related" | "combined" = "related"): WorkLink => ({ a, b, kind, weight: 0.5 });

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  // The canvas fades in and slides on timers; the tests drive it with real state, and reduced motion keeps it still.
  vi.stubGlobal("matchMedia", (q: string) => ({ matches: /prefers-reduced-motion/.test(q), media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, onchange: null, dispatchEvent: () => false }));
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); vi.unstubAllGlobals(); });

/** The canvas under a parent that owns the selection, as the screen does. */
function Harness({ graph, onSelect, start = null }: { graph: WorkGraph; onSelect?: (id: string | null) => void; start?: string | null }) {
  const [sel, setSel] = useState<string | null>(start);
  return createElement(GraphCanvas, { graph, width: 900, height: 560, selected: sel, onSelect: (id: string | null) => { setSel(id); onSelect?.(id); } });
}
const mount = (graph: WorkGraph, onSelect?: (id: string | null) => void, start: string | null = null) => {
  act(() => { root.render(createElement(Harness, { graph, onSelect, start })); });
  return { svg: host.querySelector<SVGSVGElement>("svg.gcanvas")! };
};
const nodes = () => [...host.querySelectorAll<SVGGElement>(".gnode")];
const tip = () => host.querySelector<HTMLElement>(".gtip");
const key = (el: Element, k: string) => act(() => { el.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true })); });
const enter = (el: Element) => act(() => { el.dispatchEvent(new MouseEvent("pointerover", { bubbles: true, relatedTarget: null })); });
const leave = (el: Element) => act(() => { el.dispatchEvent(new MouseEvent("pointerout", { bubbles: true, relatedTarget: document.body })); });
const click = (el: Element) => act(() => { el.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
const focus = (el: SVGElement) => act(() => { el.focus(); });

describe("the canvas writes no text", () => {
  it("draws no label, no title and no tooltip until something asks for one", () => {
    const { svg } = mount(wg);
    expect(svg.querySelectorAll("text, title, tspan").length).toBe(0);
    expect((svg.textContent ?? "").trim()).toBe("");
    expect(tip()).toBeNull();
  });
  it("gives every node an icon of its kind and an accessible name, in a list of the right size", () => {
    mount(wg);
    expect(nodes()).toHaveLength(wg.nodes.length);
    for (const g of nodes()) {
      expect(g.getAttribute("role")).toBe("option");
      expect(g.getAttribute("aria-label")).toMatch(/^(Routine|Skill|Memory|Automation): .+\. Strength \d+ percent\./);
      expect(g.getAttribute("aria-setsize")).toBe(String(wg.nodes.length));
      expect(g.querySelector(".gnode__ink .gglyph")).not.toBeNull();
    }
    const kinds = new Set(nodes().map((g) => g.getAttribute("data-kind")));
    expect([...kinds].sort()).toEqual(["automation", "memory", "routine", "skill"]);
    // One glyph drawing per kind: the shapes differ, so the kind does not rest on colour.
    const draw = (k: string) => nodes().find((g) => g.getAttribute("data-kind") === k)!.querySelector(".gglyph")!.innerHTML;
    expect(new Set(["routine", "skill", "memory", "automation"].map(draw)).size).toBe(4);
  });
  it("marks a lapsed node with a dashed ring, and says so in its name", () => {
    mount(wg);
    const lapsed = nodes().filter((g) => g.hasAttribute("data-lapsed"));
    expect(lapsed.length).toBe(wg.nodes.filter((n) => n.strength < 0.4).length);
    for (const g of lapsed) { expect(g.querySelector(".gnode__lapsed")).not.toBeNull(); expect(g.getAttribute("aria-label")).toContain("Fading."); }
  });
  it("is one tab stop: the canvas, and nothing focusable inside it", () => {
    const { svg } = mount(wg);
    expect(svg.getAttribute("tabindex")).toBe("0");
    expect(svg.getAttribute("role")).toBe("listbox");
    expect(svg.querySelectorAll("[tabindex], a, button, input").length).toBe(0);
  });
});

describe("a name appears on hover, focus and click", () => {
  it("opens a card on hover with the full name and the kind, and closes it when the pointer leaves", () => {
    mount(wg);
    const first = nodes()[0];
    enter(first);
    expect(tip()).not.toBeNull();
    expect(tip()!.textContent).toContain(wg.nodes[0].label);
    expect(tip()!.textContent).toMatch(/Routine|Skill|Memory|Automation/);
    expect(tip()!.getAttribute("aria-hidden")).toBe("true");
    leave(first);
    expect(tip()).toBeNull();
  });
  it("a click keeps the name until Escape or another click", () => {
    const picked: (string | null)[] = [];
    const { svg } = mount(wg, (id) => picked.push(id));
    const a = nodes()[0], b = nodes()[1];
    enter(a); click(a); leave(a);
    expect(picked).toEqual([wg.nodes[0].id]);
    expect(tip()).not.toBeNull();
    expect(tip()!.textContent).toContain(wg.nodes[0].label);
    expect(tip()!.hasAttribute("data-pinned")).toBe(true);
    click(b);
    expect(tip()!.textContent).toContain(wg.nodes[1].label);
    key(svg, "Escape");
    expect(picked[picked.length - 1]).toBeNull();
    expect(tip()).toBeNull();
  });
  it("a click on the empty canvas closes the selection", () => {
    const picked: (string | null)[] = [];
    mount(wg, (id) => picked.push(id), wg.nodes[0].id);
    expect(tip()).not.toBeNull();
    click(host.querySelector(".gcanvas__bg")!);
    expect(picked).toEqual([null]);
    expect(tip()).toBeNull();
  });
  it("names the node the keyboard is on, and a touch hover does not open a card", () => {
    const { svg } = mount(wg);
    focus(svg);
    expect(svg.getAttribute("aria-activedescendant")).toBe(`gn-${wg.nodes[0].id}`);
    expect(tip()!.textContent).toContain(wg.nodes[0].label);
    act(() => { svg.blur(); });
    expect(tip()).toBeNull();
    const ev = new MouseEvent("pointerover", { bubbles: true, relatedTarget: null });
    Object.defineProperty(ev, "pointerType", { value: "touch" });
    act(() => { nodes()[2].dispatchEvent(ev); });
    expect(tip()).toBeNull();
  });
});

describe("the keys", () => {
  it("arrow keys move between nodes, Enter opens one, Escape closes", () => {
    const picked: (string | null)[] = [];
    const { svg } = mount(wg, (id) => picked.push(id));
    focus(svg);
    const start = svg.getAttribute("aria-activedescendant");
    const seen = new Set<string | null>([start]);
    for (const k of ["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp", "ArrowRight", "ArrowRight"]) { key(svg, k); seen.add(svg.getAttribute("aria-activedescendant")); }
    expect(seen.size).toBeGreaterThan(2);
    key(svg, "Enter");
    expect(picked[picked.length - 1]).toBe(svg.getAttribute("aria-activedescendant")!.replace(/^gn-/, ""));
    key(svg, "Escape");
    expect(picked[picked.length - 1]).toBeNull();
  });
  it("Home, End, PageDown and PageUp walk the list and reach every node", () => {
    const { svg } = mount(wg);
    focus(svg);
    key(svg, "Home");
    expect(svg.getAttribute("aria-activedescendant")).toBe(`gn-${wg.nodes[0].id}`);
    key(svg, "End");
    expect(svg.getAttribute("aria-activedescendant")).toBe(`gn-${wg.nodes[wg.nodes.length - 1].id}`);
    key(svg, "Home");
    const seen = new Set<string | null>();
    for (let i = 0; i < wg.nodes.length; i++) { seen.add(svg.getAttribute("aria-activedescendant")); key(svg, "PageDown"); }
    expect(seen.size).toBe(wg.nodes.length);
    key(svg, "PageUp");
    expect(svg.getAttribute("aria-activedescendant")).toBe(`gn-${wg.nodes[wg.nodes.length - 1].id}`);
  });
  it("Escape hides a passing name without losing the focus", () => {
    const { svg } = mount(wg);
    focus(svg);
    expect(tip()).not.toBeNull();
    key(svg, "Escape");
    expect(tip()).toBeNull();
    expect(document.activeElement).toBe(svg);
    key(svg, "ArrowRight");
    expect(tip()).not.toBeNull();
  });
});

describe("edge cases", () => {
  it("an empty graph draws an empty list without failing", () => {
    const { svg } = mount({ nodes: [], links: [] });
    expect(nodes()).toHaveLength(0);
    expect(svg.getAttribute("aria-label")).toContain("0 nodes");
    focus(svg);
    key(svg, "ArrowRight");
    key(svg, "Enter");
    expect(tip()).toBeNull();
  });
  it("a single node sits alone, says 'node' not 'nodes', and can be named", () => {
    const { svg } = mount({ nodes: [mk("only", "memory", { label: "Short summaries" })], links: [] });
    expect(nodes()).toHaveLength(1);
    expect(svg.getAttribute("aria-label")).toContain("1 node.");
    focus(svg);
    expect(tip()!.textContent).toContain("Short summaries");
    key(svg, "ArrowRight");
    expect(svg.getAttribute("aria-activedescendant")).toBe("gn-only");
  });
  it("shows a very long label in full in the card, clamped by the stylesheet, and in the accessible name", () => {
    const long = `Reconcile ${"the household totals against the case note before you copy anything, ".repeat(8)}end`;
    mount({ nodes: [mk("long", "routine", { label: long }), mk("b")], links: [lk("long", "b")] });
    enter(nodes()[0]);
    expect(tip()!.querySelector(".gtip__name")!.textContent).toBe(long);
    expect(nodes()[0].getAttribute("aria-label")).toContain(long);
  });
  it("shows unicode labels as they are, and tells repeated labels apart by their place in the list", () => {
    const g: WorkGraph = { nodes: [mk("a", "skill", { label: "Überprüfe Kündigungsfrist 日本語 🙂" }), mk("b", "skill", { label: "Same name" }), mk("c", "skill", { label: "Same name" })], links: [] };
    mount(g);
    enter(nodes()[0]);
    expect(tip()!.textContent).toContain("Überprüfe Kündigungsfrist 日本語 🙂");
    expect(nodes()[1].getAttribute("aria-label")).toBe(nodes()[2].getAttribute("aria-label"));
    expect([nodes()[1], nodes()[2]].map((n) => n.getAttribute("aria-posinset"))).toEqual(["2", "3"]);
    expect(new Set(nodes().map((n) => n.id)).size).toBe(3);
  });
  it("copes with self-loops, repeated links, links to nothing, repeated ids and disconnected parts", async () => {
    const g: WorkGraph = { nodes: [mk("a"), mk("b"), mk("c"), mk("d"), mk("a")], links: [lk("a", "a"), lk("a", "b"), lk("b", "a", "combined"), lk("c", "ghost"), lk("c", "d")] };
    mount(g);
    // The envelope appears once the intro has run (at once, under reduced motion).
    await act(async () => { await new Promise((r) => setTimeout(r, 30)); });
    expect(nodes()).toHaveLength(4);
    expect(host.querySelectorAll(".ghull").length).toBe(1);
    expect(host.innerHTML).not.toContain("NaN");
  });
  it("names a pair that always runs together, in the name of each", () => {
    mount({ nodes: [mk("a", "routine", { label: "Enter household" }), mk("b", "routine", { label: "Open calculators" })], links: [lk("a", "b", "combined")] });
    expect(nodes()[0].getAttribute("aria-label")).toContain("Always runs with Open calculators.");
    expect(nodes()[1].getAttribute("aria-label")).toContain("Always runs with Enter household.");
  });
  it("a graph of a thousand nodes renders quickly as small shapes, with no text, and is still one tab stop", () => {
    const kinds: WorkNodeType[] = ["routine", "skill", "memory", "automation"];
    const g: WorkGraph = { nodes: Array.from({ length: 1000 }, (_, i) => mk(`n${i}`, kinds[i % 4], { size: i % 4 === 1 ? 0.5 : 40, strength: (i % 10) / 10 })), links: Array.from({ length: 1400 }, (_, i) => lk(`n${i % 1000}`, `n${(i * 7 + 3) % 1000}`)) };
    const t0 = performance.now();
    const { svg } = mount(g);
    const ms = performance.now() - t0;
    expect(nodes()).toHaveLength(1000);
    expect(svg.hasAttribute("data-dots")).toBe(true);
    expect(svg.querySelectorAll("text, title").length).toBe(0);
    expect(svg.querySelectorAll(".gglyph").length).toBe(0);
    expect(svg.querySelectorAll("[tabindex]").length).toBe(0);
    // The links are a few paths, not one element each.
    expect(host.querySelectorAll(".glink").length).toBeLessThanOrEqual(6);
    expect(ms).toBeLessThan(15000);
    enter(nodes()[500]);
    expect(tip()).not.toBeNull();
  });
});

describe("the key", () => {
  const mountKey = () => { act(() => { root.render(createElement(GraphLegend, { entries: WORK_LEGEND })); }); };
  it("sits behind a small disclosure that is closed to begin with", () => {
    mountKey();
    const d = host.querySelector("details")!;
    expect(d.open).toBe(false);
    expect(d.querySelector("summary")!.textContent).toBe("What are these?");
  });
  it("is pictures: no text of its own, each picture a button with its name and meaning in its aria-label", () => {
    mountKey();
    const items = [...host.querySelectorAll<HTMLButtonElement>(".gkey__item")];
    expect(items).toHaveLength(WORK_LEGEND.length);
    for (const b of items) { expect((b.textContent ?? "").trim()).toBe(""); expect(b.getAttribute("aria-label")).toMatch(/^[A-Z][a-z]+: .+/); expect(b.querySelector("svg")).not.toBeNull(); }
    expect(items.slice(0, 4).map((b) => b.getAttribute("aria-label")!.split(":")[0])).toEqual(["Routine", "Skill", "Memory", "Automation"]);
  });
  it("opens a card for a tap and closes it for Escape or a second tap", () => {
    mountKey();
    const b = host.querySelector<HTMLButtonElement>(".gkey__item")!;
    click(b);
    expect(b.getAttribute("aria-expanded")).toBe("true");
    key(b, "Escape");
    expect(b.getAttribute("aria-expanded")).toBe("false");
    click(b); click(b);
    expect(b.getAttribute("aria-expanded")).toBe("false");
  });
});
