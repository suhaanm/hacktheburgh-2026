// @vitest-environment jsdom
// The Growth sections below the fold read their data only when they are near the screen or named by the address.
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WhenNear } from "./GrowthSection";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;
let observers: { cb: IntersectionObserverCallback; disconnect: ReturnType<typeof vi.fn>; opts?: IntersectionObserverInit }[] = [];
let mounted = 0;

function Probe() {
  mounted += 1;                                                              // stands for a section that starts its reads when it mounts
  return createElement("p", { id: "real" }, "the real section");
}
const render = (open = false) => act(async () => { root.render(createElement(WhenNear, { id: "time", title: "Where my time goes", headline: "Reading your week.", open }, createElement(Probe))); });

beforeEach(() => {
  mounted = 0;
  observers = [];
  vi.stubGlobal("IntersectionObserver", class {
    disconnect = vi.fn();
    constructor(public cb: IntersectionObserverCallback, public opts?: IntersectionObserverInit) { observers.push(this as never); }
    observe() {}
  });
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); vi.unstubAllGlobals(); });

describe("a section below the fold", () => {
  it("shows a placeholder with its own id and title and reads nothing until it is within 400 px of the screen", async () => {
    await render();
    expect(mounted).toBe(0);
    expect(host.querySelector("#real")).toBeNull();
    expect(host.querySelector("#gr-time")?.getAttribute("aria-label")).toBe("Where my time goes");
    expect(observers[0]?.opts?.rootMargin).toBe("400px 0px");
    await act(async () => { observers[0].cb([{ isIntersecting: false } as IntersectionObserverEntry], observers[0] as never); });
    expect(mounted).toBe(0);                                                   // near is not the same as "an observation happened"
    await act(async () => { observers[0].cb([{ isIntersecting: true } as IntersectionObserverEntry], observers[0] as never); });
    expect(host.querySelector("#real")).not.toBeNull();
    expect(mounted).toBeGreaterThan(0);
    expect(observers[0].disconnect).toHaveBeenCalled();
  });

  it("loads at once when the address names it", async () => {
    await render(true);
    expect(host.querySelector("#real")).not.toBeNull();
  });

  it("loads at once where there is no IntersectionObserver", async () => {
    vi.stubGlobal("IntersectionObserver", undefined);
    await render();
    expect(host.querySelector("#real")).not.toBeNull();
  });
});
