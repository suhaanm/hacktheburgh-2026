// @vitest-environment jsdom
// The Graph screen on its own and embedded in a section of another screen (Growth, "My routines map"): embedded it draws no title, no origin badge and no page
// wrapper, only the canvas, the key and the foot; on its own it draws the title and the same headline sentence.
import { createElement, act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import fx from "../fixtures/workgraph.json";
import type { WorkGraph } from "../types";
import { graphHeadline } from "../lib/graph";

const wg = (fx as unknown as { data: WorkGraph }).data;
const meta = (fx as unknown as { meta: unknown }).meta;
const api = vi.hoisted(() => ({ workGraph: vi.fn(), memory: vi.fn(), putMemory: vi.fn(), deleteWorkNode: vi.fn() }));
vi.mock("../api", () => ({
  ApiError: class ApiError extends Error { status: number; code: string; constructor(status: number, code: string, message: string) { super(message); this.status = status; this.code = code; } },
  api,
}));
import Graph from "./Graph";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({ width: 900, height: 600, top: 0, left: 0, right: 900, bottom: 600, x: 0, y: 0, toJSON: () => ({}) });
  api.workGraph.mockReset().mockResolvedValue({ data: structuredClone(wg), meta: structuredClone(meta), source: "demo", why: null });
  api.memory.mockReset().mockReturnValue(new Promise(() => undefined));
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

async function mount(props: { embedded?: boolean } = {}) {
  await act(async () => { root.render(createElement(Graph, props)); });
  await act(async () => { await Promise.resolve(); });
}

describe("the Graph screen", () => {
  it("on its own: a page with the title and the headline, then the canvas and the key (generated people draw no origin badge)", async () => {
    await mount();
    expect(host.querySelector(".page")).not.toBeNull();
    expect(host.querySelector("h1")!.textContent).toBe("How your work connects");
    expect(host.querySelector(".screenhead__limit")!.textContent).toBe(graphHeadline(wg));
    expect(host.querySelector(".pill--origin")).toBeNull(); // generated people carry no badge (owner decision D57); only a fixture fallback prints one
    expect(host.querySelector("svg.gcanvas")).not.toBeNull();
    expect(host.querySelector(".gkey")).not.toBeNull();
  });
  it("embedded: no title, no origin badge, no page wrapper; the canvas, the key and the foot remain", async () => {
    await mount({ embedded: true });
    expect(host.querySelector("h1, h2.screenhead__title, .screenhead")).toBeNull();
    expect(host.querySelector(".page")).toBeNull();
    expect(host.querySelector(".pill--origin")).toBeNull();
    expect(host.querySelector("svg.gcanvas")).not.toBeNull();
    expect(host.querySelector(".gkey")).not.toBeNull();
    // The origin stays in the foot's "About this data" rows.
    const foot = host.querySelector(".chart__foot")!;
    expect(foot.textContent).toContain("About this data");
    expect(foot.textContent).toMatch(/where from/);
  });
  it("embedded, an empty graph shows the empty state without a page wrapper", async () => {
    api.workGraph.mockResolvedValue({ data: { nodes: [], links: [] }, meta, source: "demo", why: null });
    await mount({ embedded: true });
    expect(host.querySelector(".page")).toBeNull();
    expect(host.querySelector(".state__title")!.textContent).toBe("Nothing here yet");
  });
  it("on its own, an empty graph has a title and no headline", async () => {
    api.workGraph.mockResolvedValue({ data: { nodes: [], links: [] }, meta, source: "demo", why: null });
    await mount();
    expect(host.querySelector("h1")).not.toBeNull();
    expect(host.querySelector(".screenhead__limit")).toBeNull();
  });
});
