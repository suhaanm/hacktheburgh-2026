// @vitest-environment jsdom
// The shared SourceNote as the Repeats page uses it: one plain visible line from the shared EXAMPLE_LINE for every kind of fallback, and the
// engine's full sentence (flag name included) in a closed in-place Details, never in the first line a worker reads.
import { createElement as h } from "react";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { EXAMPLE_LINE, type Fallback } from "../../lib/fallback";
import { SourceNote } from "../common";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement;
let root: Root;
beforeEach(() => { host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); });

const RAW = "This feature is switched off in The engine. Start it with UNDERSTUDY_X_HITLIST=1 (or UNDERSTUDY_X=1 for every extension) to see your own data.";
const why = (kind: Fallback["kind"]): Fallback => ({ kind, status: 404, code: "not_found", message: RAW });

describe("example data note on the Repeats page", () => {
  it("for every kind prints the one plain line and keeps the engine's sentence in a closed Details", () => {
    for (const k of ["offline", "extension_off", "missing", "error"] as const) {
      act(() => root.render(h(SourceNote, { why: why(k) })));
      const wrap = host.querySelector(".sourcenote")!;
      expect(wrap.getAttribute("data-kind")).toBe(k);
      const line = wrap.querySelector("p.note")!;
      expect(line.textContent).toBe(EXAMPLE_LINE[k]);
      expect(line.textContent).not.toContain("UNDERSTUDY_X");
      const details = wrap.querySelector("details")!;
      expect(details.open).toBe(false);
      expect(details.querySelector("summary")?.textContent).toBe("Details");
      expect(details.querySelector("[data-testid=source-detail]")?.textContent).toBe(RAW);
    }
    expect(EXAMPLE_LINE.offline).toBe("Showing example data: the engine is not answering yet.");
  });

  it("draws nothing when the data is live", () => {
    act(() => root.render(h(SourceNote, { why: null })));
    expect(host.innerHTML).toBe("");
  });
});
