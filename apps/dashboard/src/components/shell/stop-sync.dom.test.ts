// @vitest-environment jsdom
// Stop everything and Resume can come from OUTSIDE the Knack window (the corner pill, the menu bar, the Dock menu, a hotkey). The open window must follow within a few seconds:
// the sidebar button turns from Stop to Resume and the "Everything is stopped" banner appears, and the other way round when something outside resumes. Before this the state was read
// once at page load, so a Resume from the corner card left the banner and the Resume button in the window until it was reloaded.
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setState } from "../../store";

const api = vi.hoisted(() => ({ killState: vi.fn(), kill: vi.fn(), clearKill: vi.fn() }));
vi.mock("../../api", () => ({ ApiError: class ApiError extends Error {}, api }));
import { KILL_POLL_MS, KILL_POLL_UNFOCUSED_MS, StopButton, StopProvider, StoppedBanner } from "./StopControl";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;
let outside = { killed: false, at: null as string | null };
const reply = () => Promise.resolve({ data: { killed: outside.killed, at: outside.at }, meta: null, source: "live" });

beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(document, "hasFocus").mockReturnValue(true);        // the window being looked at: the 3 s pace (jsdom reports no focus)
  outside = { killed: false, at: null };
  setState({ killed: false, killedAt: null, killError: null });
  api.killState.mockReset().mockImplementation(reply);
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); vi.useRealTimers(); vi.restoreAllMocks(); });

const text = () => host.textContent ?? "";
const button = () => host.querySelector<HTMLButtonElement>(".stop-button")?.textContent ?? "";
async function mount(): Promise<void> {
  await act(async () => { root.render(createElement(StopProvider, null, createElement("div", null, createElement(StopButton), createElement(StoppedBanner)))); });
  await act(async () => { await vi.advanceTimersByTimeAsync(10); });
}
async function wait(ms: number): Promise<void> {
  await act(async () => { await vi.advanceTimersByTimeAsync(ms); });
}

describe("the window follows Stop everything and Resume that happen outside it", () => {
  it("polls at least every 4 seconds", () => {
    expect(KILL_POLL_MS).toBeLessThanOrEqual(4000);
  });

  it("a stop from the corner pill, the menu bar or the hotkey shows the banner and Resume within 4 seconds", async () => {
    await mount();
    expect(button()).toBe("Stop");
    expect(text()).not.toContain("Everything is stopped");
    outside = { killed: true, at: new Date().toISOString() };
    await wait(4000);
    expect(button()).toBe("Resume");
    expect(text()).toContain("Everything is stopped");
  });

  it("a Resume from the corner card, the menu bar or the Dock menu clears the banner and the sidebar Stop within 4 seconds", async () => {
    outside = { killed: true, at: new Date().toISOString() };
    await mount();
    expect(button()).toBe("Resume");
    expect(text()).toContain("Everything is stopped");
    outside = { killed: false, at: null };
    await wait(4000);
    expect(button()).toBe("Stop");
    expect(text()).not.toContain("Everything is stopped");
  });

  it("looking at the window again reads it at once (no waiting for the next tick)", async () => {
    await mount();
    outside = { killed: true, at: new Date().toISOString() };
    await act(async () => { window.dispatchEvent(new Event("focus")); await vi.advanceTimersByTimeAsync(5); });
    expect(button()).toBe("Resume");
  });

  it("a service that does not answer leaves what the window showed, and nothing is thrown", async () => {
    outside = { killed: true, at: new Date().toISOString() };
    await mount();
    api.killState.mockReset().mockRejectedValue(new Error("down"));
    await wait(KILL_POLL_MS * 2);
    expect(button()).toBe("Resume");
  });

  it("asks every 5 s, not every 3 s, while the window is visible but not the one in use, and never twice at once", async () => {
    await mount();
    vi.mocked(document.hasFocus).mockReturnValue(false);
    await wait(KILL_POLL_MS);                                  // the timer already armed fires on the old pace once, then re-arms at 5 s
    const base = api.killState.mock.calls.length;
    await wait(KILL_POLL_UNFOCUSED_MS - 100);
    expect(api.killState.mock.calls.length).toBe(base);
    await wait(200);
    expect(api.killState.mock.calls.length).toBe(base + 1);
    let release: () => void = () => undefined;
    api.killState.mockReset().mockImplementation(() => new Promise((resolve) => { release = () => resolve({ data: { killed: false, at: null }, meta: null, source: "live" }); }));
    await wait(KILL_POLL_UNFOCUSED_MS * 3);                    // the first of these is still unanswered: no second request while it waits
    expect(api.killState.mock.calls.length).toBe(1);
    release();
  });

  it("stops asking when the window is gone", async () => {
    await mount();
    const before = api.killState.mock.calls.length;
    act(() => root.unmount());
    await vi.advanceTimersByTimeAsync(KILL_POLL_MS * 3);
    expect(api.killState.mock.calls.length).toBe(before);
    root = createRoot(host); // so the shared afterEach can unmount a live root
  });
});
