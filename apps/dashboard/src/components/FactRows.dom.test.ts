// @vitest-environment jsdom
// FactRows is a label : value list. Two facts may share a label (the steps list has two "Enter household" rows), so the row key must not be the label alone:
// a repeated key makes React warn and can drop or duplicate a row.
import { afterEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { createRoot } from "react-dom/client";
import { act } from "react";
import { FactRows } from "./ui";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

afterEach(() => { vi.restoreAllMocks(); document.body.innerHTML = ""; });

describe("FactRows", () => {
  it("draws every row, even when two rows share a label, with no duplicate-key warning", async () => {
    const warn = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(createElement(FactRows, { rows: [["Enter household", "12 s"], ["Enter household", "9 s"], ["Read result", "4 s"]] }));
    });
    expect(host.querySelectorAll("dt").length).toBe(3);
    expect(host.querySelectorAll("dd").length).toBe(3);
    expect([...host.querySelectorAll("dd")].map((d) => d.textContent)).toEqual(["12 s", "9 s", "4 s"]);
    expect(warn.mock.calls.some((c) => String(c[0]).includes("same key"))).toBe(false);
    await act(async () => { root.unmount(); });
  });
});
