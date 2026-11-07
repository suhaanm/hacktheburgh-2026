import { describe, expect, it } from "vitest";
import { HINT_CLOSED, hintReduce, isHintOpen, placeHint, type HintEvent, type HintState } from "./hint-logic";

const run = (events: HintEvent[], from: HintState = HINT_CLOSED) => events.reduce(hintReduce, from);

describe("Hint state", () => {
  it("is closed at rest", () => {
    expect(isHintOpen(HINT_CLOSED)).toBe(false);
  });

  it("opens on pointer enter and closes on leave", () => {
    expect(isHintOpen(run(["enter"]))).toBe(true);
    expect(isHintOpen(run(["enter", "leave"]))).toBe(false);
  });

  it("opens on keyboard focus and closes on blur", () => {
    expect(isHintOpen(run(["focus"]))).toBe(true);
    expect(isHintOpen(run(["focus", "blur"]))).toBe(false);
  });

  it("a click pins it open, so it stays after the pointer leaves, and a second click closes it", () => {
    const pinned = run(["enter", "click", "leave"]);
    expect(isHintOpen(pinned)).toBe(true);
    const closed = run(["click"], pinned);
    expect(isHintOpen(closed)).toBe(false);
  });

  it("a second click closes it even while the pointer or focus is still on it, until the next enter or focus", () => {
    const s = run(["enter", "focus", "click", "click"]);
    expect(isHintOpen(s)).toBe(false);
    expect(isHintOpen(hintReduce(s, "enter"))).toBe(true);
  });

  it("Escape closes it everywhere and keeps focus, and it stays closed until the next focus, enter or click", () => {
    const s = run(["focus", "enter", "click", "escape"]);
    expect(isHintOpen(s)).toBe(false);
    expect(s.focus).toBe(true);
    expect(isHintOpen(hintReduce(s, "leave"))).toBe(false);
    expect(isHintOpen(hintReduce(s, "click"))).toBe(true);
    expect(isHintOpen(hintReduce(s, "enter"))).toBe(true);
  });

  it("a tap elsewhere closes everything", () => {
    expect(isHintOpen(run(["enter", "focus", "click", "outside"]))).toBe(false);
  });

  it("blur drops a pinned note", () => {
    expect(isHintOpen(run(["focus", "click", "blur"]))).toBe(false);
  });
});

describe("Hint placement", () => {
  const vp = { w: 390, h: 844 };
  it("sits under the button, centred, when it fits", () => {
    const p = placeHint({ left: 195, top: 100, width: 24, height: 24 }, { w: 200, h: 60 }, vp);
    expect(p.side).toBe("below");
    expect(p.y).toBe(100 + 24 + 8);
    expect(p.x).toBe(195 + 12 - 100);
  });
  it("is kept inside the screen on both edges", () => {
    expect(placeHint({ left: 2, top: 100, width: 24, height: 24 }, { w: 280, h: 60 }, vp).x).toBe(8);
    expect(placeHint({ left: 370, top: 100, width: 24, height: 24 }, { w: 280, h: 60 }, vp).x).toBe(390 - 280 - 8);
  });
  it("goes above the button when there is no room below", () => {
    const p = placeHint({ left: 100, top: 800, width: 24, height: 24 }, { w: 200, h: 80 }, vp);
    expect(p.side).toBe("above");
    expect(p.y).toBe(800 - 8 - 80);
  });
  it("goes below when neither side fits, because the page can scroll", () => {
    const p = placeHint({ left: 100, top: 20, width: 24, height: 24 }, { w: 200, h: 900 }, vp);
    expect(p.side).toBe("below");
  });
});
