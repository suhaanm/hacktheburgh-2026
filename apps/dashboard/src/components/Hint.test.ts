// @vitest-environment jsdom
// The Hint component in a real DOM: keyboard open and close, Escape, focus staying on the button, and the aria wiring.
import { createElement, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Hint } from "./Hint";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;

const mount = (outerKey?: (e: KeyboardEvent) => void) => {
  act(() => {
    root.render(
      createElement(
        "div",
        { id: "outer", onKeyDown: outerKey ? (e: ReactKeyboardEvent) => outerKey(e.nativeEvent) : undefined },
        createElement("p", null, "14 min ", createElement(Hint, { label: "Range for minutes", children: "9 to 19 min a week, 95% interval" })),
        createElement("button", { id: "other", type: "button" }, "Other"),
      ),
    );
  });
  const btn = host.querySelector<HTMLButtonElement>(".hint__btn")!;
  const note = host.querySelector<HTMLElement>(".hint__pop")!;
  return { btn, note };
};

beforeEach(() => {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

describe("Hint component", () => {
  it("is a button with a name, collapsed, and a note that describes it", () => {
    const { btn, note } = mount();
    expect(btn.tagName).toBe("BUTTON");
    expect(btn.getAttribute("type")).toBe("button");
    expect(btn.getAttribute("aria-label")).toBe("Range for minutes");
    expect(btn.getAttribute("aria-expanded")).toBe("false");
    expect(btn.getAttribute("aria-describedby")).toBe(note.id);
    expect(note.getAttribute("role")).toBe("note");
    expect(note.hidden).toBe(true);
    expect(note.textContent).toBe("9 to 19 min a week, 95% interval");
  });

  it("opens on keyboard focus", () => {
    const { btn, note } = mount();
    act(() => btn.focus());
    expect(btn.getAttribute("aria-expanded")).toBe("true");
    expect(note.hidden).toBe(false);
  });

  it("Escape closes it, keeps focus on the button, and does not reach an enclosing handler", () => {
    const seen: string[] = [];
    const { btn, note } = mount((e) => seen.push(e.key));
    act(() => btn.focus());
    expect(note.hidden).toBe(false);
    act(() => { btn.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true })); });
    expect(note.hidden).toBe(true);
    expect(btn.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(btn);
    expect(seen).toEqual([]);
  });

  it("Escape passes through when the hint is closed, so an enclosing panel can still close", () => {
    const seen: string[] = [];
    const { btn } = mount((e) => seen.push(e.key));
    act(() => { btn.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true })); });
    expect(seen).toEqual(["Escape"]);
  });

  it("a click pins it, a second click closes it", () => {
    const { btn, note } = mount();
    act(() => btn.click());
    expect(note.hidden).toBe(false);
    act(() => btn.click());
    expect(note.hidden).toBe(true);
  });

  it("closes when focus moves to another control, and when the page is pressed elsewhere", () => {
    const { btn, note } = mount();
    act(() => btn.focus());
    expect(note.hidden).toBe(false);
    act(() => host.querySelector<HTMLButtonElement>("#other")!.focus());
    expect(note.hidden).toBe(true);
    act(() => btn.click());
    expect(note.hidden).toBe(false);
    act(() => { document.body.dispatchEvent(new Event("pointerdown", { bubbles: true })); });
    expect(note.hidden).toBe(true);
  });

  it("has no link or button inside the note", () => {
    const { note } = mount();
    expect(note.querySelector("a, button, input")).toBeNull();
  });
});
