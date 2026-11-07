// @vitest-environment jsdom
import { createElement as h } from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { exampleFirm, exampleHitlist } from "../../fixtures/repeats";
import { HitList } from "./HitList";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;
beforeEach(() => { host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); });

const week = exampleHitlist(7);
const rows = () => Array.from(host.querySelectorAll<HTMLLIElement>("ul.hitlist:not(.hl-fold__list) > li.hitrow"));
const key = (el: Element, k: string) => act(() => { el.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true })); });

function mount(props: Record<string, unknown> = {}) {
  act(() => root.render(h(HitList, { rows: week.rows, automated: week.automated, windowDays: 7, renderPeek: (r: { label: string }, close: () => void) => h("div", { "data-testid": "peek" }, r.label, h("button", { onClick: close }, "Close")), onHide: vi.fn(), ...props })));
}

describe("worker list", () => {
  it("shows seven rows and a Show all line, with the key part bold and the count in brackets", () => {
    mount();
    expect(rows()).toHaveLength(7);
    expect(host.querySelector(".hl-more")?.textContent).toBe(`Show all ${week.rows.length}`);
    const first = rows()[0];
    expect(first.querySelector(".hitrow__label b")?.textContent).toBe("household");
    expect(first.querySelector(".hitrow__label")?.textContent).toBe("Enter the household into three calculators");
    expect(first.querySelector(".hitrow__count")?.textContent).toBe("(15 times)");
    expect(first.querySelector(".hitrow__value")?.textContent).toContain("53 min");
    act(() => host.querySelector<HTMLButtonElement>(".hl-more")!.click());
    expect(rows()).toHaveLength(week.rows.length);
    expect(host.querySelector(".hl-more")?.textContent).toBe("Show fewer");
  });

  it("puts a chip only on rows where something is already happening", () => {
    mount();
    const chips = rows().map((r) => r.querySelector(".hl-chip")?.textContent ?? null);
    expect(chips.filter(Boolean).sort()).toEqual(["learning", "proposed", "running"]);
    expect(rows().filter((r) => !r.querySelector(".hl-chip"))).not.toHaveLength(0);
  });

  it("offers one tab stop for the list: the active row, its buttons and its Hint; arrows move the stop", () => {
    mount();
    const stops = () => rows().map((r, i) => `${i}:${r.tabIndex}:${Array.from(r.querySelectorAll("button")).filter((b) => b.tabIndex === 0).length}`);
    expect(rows().map((r) => r.tabIndex)).toEqual([0, -1, -1, -1, -1, -1, -1]);
    expect(rows().slice(1).every((r) => Array.from(r.querySelectorAll("button")).every((b) => b.tabIndex === -1))).toBe(true);
    act(() => rows()[0].focus());
    key(rows()[0], "ArrowDown");
    key(rows()[1], "ArrowDown");
    expect(document.activeElement).toBe(rows()[2]);
    expect(rows().map((r) => r.tabIndex)).toEqual([-1, -1, 0, -1, -1, -1, -1]);
    expect(Array.from(rows()[2].querySelectorAll("button")).every((b) => b.tabIndex === 0)).toBe(true);
    expect(stops()[0]).toBe("0:-1:0");
    key(rows()[2], "End");
    expect(document.activeElement).toBe(rows()[6]);
    key(rows()[6], "Home");
    expect(document.activeElement).toBe(rows()[0]);
  });

  it("Enter opens the Automate peek under the row, Escape closes it and puts focus back on the row", () => {
    mount();
    act(() => rows()[0].focus());
    key(rows()[0], "Enter");
    expect(host.querySelector("[data-testid=peek]")?.textContent).toContain("Enter the household into three calculators");
    expect(rows()[0].dataset.open).toBe("true");
    expect(rows()[0].querySelector("button[aria-expanded]")?.getAttribute("aria-expanded")).toBe("true");
    key(host.querySelector("[data-testid=peek]")!, "Escape");
    expect(host.querySelector("[data-testid=peek]")).toBeNull();
    expect(document.activeElement).toBe(rows()[0]);
    // pressing Enter on a button inside the row is the button's own business, not the row's
    const btn = rows()[0].querySelector<HTMLButtonElement>("button.btn--secondary")!;
    key(btn, "Enter");
    expect(host.querySelector("[data-testid=peek]")).toBeNull();
    act(() => btn.click());
    expect(host.querySelector("[data-testid=peek]")).not.toBeNull();
    act(() => host.querySelector<HTMLButtonElement>("[data-testid=peek] button")!.click());
    expect(document.activeElement).toBe(rows()[0]);
  });

  it("Not this one calls onHide with the row", () => {
    const onHide = vi.fn();
    mount({ onHide });
    act(() => Array.from(rows()[1].querySelectorAll("button")).find((b) => b.textContent === "Not this one")!.click());
    expect(onHide).toHaveBeenCalledTimes(1);
    expect(onHide.mock.calls[0][0].id).toBe(week.rows[1].id);
  });

  it("a tap on a row picks it (its actions show on narrow screens); a tap on a button does not", () => {
    mount();
    act(() => rows()[3].click());
    expect(rows()[3].dataset.picked).toBe("true");
    act(() => rows()[3].click());
    expect(rows()[3].dataset.picked).toBeUndefined();
    act(() => rows()[3].querySelector<HTMLButtonElement>("button.btn--secondary")!.click());
    expect(rows()[3].dataset.picked).toBeUndefined();
  });

  it("no Automate button without a peek renderer, no Not this one without onHide, and an empty list draws no frame", () => {
    mount({ renderPeek: undefined, onHide: undefined });
    expect(host.querySelectorAll("button.btn").length).toBe(0);
    mount({ rows: [], automated: [] });
    expect(host.querySelector("ul.hitlist")).toBeNull();
  });

  it("folds the rows that are already automated, with no actions", () => {
    mount();
    const fold = host.querySelector("details.hl-fold")!;
    expect(fold.querySelector("summary")?.textContent).toContain("Already automated");
    expect(fold.querySelectorAll("li.hitrow")).toHaveLength(1);
    expect(fold.querySelectorAll("button.btn")).toHaveLength(0);
    expect(fold.querySelector(".hl-chip")?.textContent).toBe("automated");
  });

  it("says in plain words what overlaps", () => {
    mount();
    expect(host.textContent).toContain("Includes the steps of “Open the previous case from the queue”");
  });
});

describe("admin list", () => {
  it("shows people and hours a week with the interval printed, and no actions or Hint", () => {
    const firm = exampleFirm(7);
    mount({ audience: "admin", rows: firm.rows, automated: undefined, renderPeek: undefined, onHide: undefined });
    expect(rows()).toHaveLength(firm.rows.length);
    const first = rows()[0];
    expect(first.querySelector(".hitrow__count")?.textContent).toBe("(32 people)");
    expect(first.querySelector(".hitrow__value")?.textContent).toBe("29 h a week");
    expect(first.querySelector(".hitrow__sub")?.textContent).toMatch(/^benefits processor\. 28 to 31 h a week \(95% interval\), 448 times in 7 days\.$/);
    expect(host.querySelectorAll("button.btn, .hint__btn").length).toBe(0);
    expect(host.textContent).not.toContain("Automate");
  });
});
