// @vitest-environment jsdom
// ConfirmRow in a real DOM: the safe choice has the focus when the row opens, Escape means Keep, and no key confirms.
import { createElement, act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ConfirmRow, Rows } from "./ui";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;
beforeEach(() => { host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); });

function mount(onConfirm: () => void, onCancel: () => void) {
  act(() => {
    root.render(createElement(Rows, null, createElement(ConfirmRow, { question: "Forget this line?", consequence: "It cannot be undone.", confirmLabel: "Forget it", onConfirm, onCancel })));
  });
}

describe("ConfirmRow behaviour", () => {
  it("puts the focus on Keep, the safe choice, when it opens", () => {
    mount(vi.fn(), vi.fn());
    expect(document.activeElement?.textContent).toBe("Keep");
  });

  it("Escape means Keep, and no key confirms", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    mount(onConfirm, onCancel);
    const group = host.querySelector('[role="group"]')!;
    act(() => { group.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
    expect(onCancel).toHaveBeenCalledTimes(1);
    act(() => { group.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })); });
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("the confirm word is a real click", () => {
    const onConfirm = vi.fn();
    mount(onConfirm, vi.fn());
    const confirm = [...host.querySelectorAll("button")].find((b) => b.textContent === "Forget it")!;
    act(() => { confirm.click(); });
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
