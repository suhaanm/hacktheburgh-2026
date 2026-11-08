// @vitest-environment jsdom
// The details panel in a real DOM: the insight comes first (what it is, why it exists), the numbers sit behind a closed disclosure, the actions keep their
// old names, and a very long name or reason is cut in the title and printed whole under The numbers.
import { createElement, act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import memoryFx from "../../fixtures/memory.json";
import workFx from "../../fixtures/workgraph.json";
import type { WorkGraph, WorkNode } from "../../types";

const api = vi.hoisted(() => ({ memory: vi.fn(), putMemory: vi.fn(), deleteWorkNode: vi.fn() }));
vi.mock("../../api", () => ({
  ApiError: class ApiError extends Error { status: number; code: string; constructor(status: number, code: string, message: string) { super(message); this.status = status; this.code = code; } },
  api,
}));
import { NodePanel } from "./NodePanel";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const wg = (workFx as unknown as { data: WorkGraph }).data;
const memory = (memoryFx as unknown as { data: unknown }).data;
const node = (id: string, over: Partial<WorkNode> = {}): WorkNode => ({ ...wg.nodes.find((n) => n.id === id)!, ...over });

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  api.memory.mockReset().mockResolvedValue({ data: structuredClone(memory), meta: null, source: "live", why: null });
  api.putMemory.mockReset().mockResolvedValue({});
  api.deleteWorkNode.mockReset().mockResolvedValue({});
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); });

async function mount(n: WorkNode, over: { onClose?: () => void; onChanged?: () => void } = {}) {
  await act(async () => { root.render(createElement(NodePanel, { node: n, graph: wg, onClose: over.onClose ?? (() => undefined), onChanged: over.onChanged ?? (() => undefined) })); });
  await act(async () => { await Promise.resolve(); });
}
const text = () => host.textContent ?? "";
const btn = (name: string | RegExp) => [...host.querySelectorAll<HTMLButtonElement>("button")].find((b) => (typeof name === "string" ? b.textContent === name : name.test(b.textContent ?? "")))!;
const click = (el: Element) => act(async () => { el.dispatchEvent(new MouseEvent("click", { bubbles: true })); });

describe("the details panel", () => {
  it("leads with the insight: the kind, the name, what it is in one line, why it exists in one line", async () => {
    const n = node("calc-entry-3x");
    await mount(n);
    expect(host.querySelector(".gkind")).not.toBeNull();
    expect(host.querySelector(".t-label")!.textContent).toBe("Routine");
    expect(host.querySelector("h2")!.textContent).toBe(n.label);
    expect(host.querySelector(".gpanel__what")!.textContent).toBe("Steps you repeat in much the same way.");
    // What is open to read (outside the closed disclosure) is the first sentence only.
    const open = host.cloneNode(true) as HTMLElement;
    open.querySelectorAll("details").forEach((d) => d.remove());
    expect(open.textContent).toContain("Why it exists");
    expect(open.textContent).toContain("Seen 14 times in 3 weeks with almost the same steps each time.");
    expect(open.textContent).not.toContain("you have not turned it on yet");
    expect(open.textContent).not.toContain("Strength");
  });
  it("keeps the numbers behind a closed disclosure, and puts the whole reason there", async () => {
    await mount(node("calc-entry-3x"));
    const d = [...host.querySelectorAll("details")].find((x) => x.querySelector("summary")!.textContent === "The numbers")!;
    expect(d.open).toBe(false);
    const dts = [...d.querySelectorAll("dt")].map((x) => x.textContent);
    expect(dts).toEqual(expect.arrayContaining(["Strength", "Last seen", "Size", "Linked to", "In full"]));
    expect(d.querySelector("dd")!.textContent).toMatch(/94%/);
    expect(d.textContent).toContain("about 96 min a week");
    expect(d.textContent).toContain("you have not turned it on yet");
  });
  it("cuts a very long name in the title and prints it whole under The numbers", async () => {
    const long = `Reconcile ${"the household totals against the case note, ".repeat(8)}end`;
    await mount(node("calc-entry-3x", { label: long }));
    expect(host.querySelector("h2")!.textContent).toBe(long);
    const d = [...host.querySelectorAll("details")].find((x) => x.querySelector("summary")!.textContent === "The numbers")!;
    expect([...d.querySelectorAll("dt")].map((x) => x.textContent)).toContain("Full name");
    // A short name needs no second copy.
    await mount(node("calc-entry-3x"));
    expect(text()).not.toContain("Full name");
  });
  it("says a node is fading in words, and shows a skill's mastery only when the size is a fraction", async () => {
    await mount(node("calc-entry-3x", { strength: 0.2 }));
    expect(text()).toContain("20%, fading");
    await mount(node("calc-entry-3x", { type: "skill", size: 0.45 }));
    expect(text()).toContain("mastery 45%");
    await mount(node("calc-entry-3x", { type: "skill", size: 45 }));
    expect(text()).not.toContain("mastery");
  });
  it("closes with the Close button", async () => {
    const onClose = vi.fn();
    await mount(node("calc-entry-3x"), { onClose });
    await click(btn("Close"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
  it("a memory line is edited behind an Edit button, saved to the memory file, and cancelled without a trace", async () => {
    const onChanged = vi.fn();
    await mount(node("mem-short"), { onChanged });
    expect(host.querySelector("textarea")).toBeNull();
    await click(btn("Edit this line"));
    const ta = host.querySelector<HTMLTextAreaElement>("textarea")!;
    expect(ta).not.toBeNull();
    expect(btn("Save").disabled).toBe(true);
    await click(btn("Cancel"));
    expect(host.querySelector("textarea")).toBeNull();
    expect(api.putMemory).not.toHaveBeenCalled();
  });
  it("asks before it removes, in the old words, and removes only on the second click", async () => {
    const onChanged = vi.fn();
    await mount(node("mem-short"), { onChanged });
    expect(btn("Yes, remove")).toBeUndefined();
    await click(btn("Forget this line"));
    expect(text()).toContain("This removes the line from your memory file");
    await click(btn("Keep it"));
    expect(api.deleteWorkNode).not.toHaveBeenCalled();
    await click(btn("Forget this line"));
    await click(btn("Yes, remove"));
    expect(api.deleteWorkNode).toHaveBeenCalledTimes(1);
    expect(onChanged).toHaveBeenCalledTimes(1);
  });
  it("names the action for each kind", async () => {
    await mount(node("calc-entry-3x"));
    expect(btn("Never for this")).toBeDefined();
    await mount(node("calc-entry-3x", { type: "skill" }));
    expect(btn("Forget this skill")).toBeDefined();
    await mount(node("calc-entry-3x", { type: "memory" }));
    expect(btn("Forget this line")).toBeDefined();
  });
  it("a node Knack keeps cannot be edited or removed by hand, and says so", async () => {
    await mount(node("calc-entry-3x", { editable: false }));
    expect(text()).toContain("kept by Knack");
    expect(btn("Never for this")).toBeUndefined();
    expect(btn("Edit this line")).toBeUndefined();
  });
  it("shows an error in words when removing fails", async () => {
    api.deleteWorkNode.mockRejectedValueOnce(new Error("boom"));
    await mount(node("mem-short"));
    await click(btn("Forget this line"));
    await click(btn("Yes, remove"));
    expect(host.querySelector('[role="alert"]')!.textContent).toBe("Could not remove it. Try again.");
  });
});
