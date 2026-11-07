import { beforeEach, describe, expect, it } from "vitest";
import { resolveRect } from "../src/content/rect";
import { hashLabel } from "../src/shared/hash";
import { ajvFor, matcher, SALT, setPage } from "./helpers";

const validate = ajvFor("ext_rect.schema.json");
const q = (s: string) => document.querySelector(s) as HTMLElement;

function layout(el: Element, r: { x: number; y: number; w: number; h: number }) {
  (el as HTMLElement).getBoundingClientRect = () =>
    ({ left: r.x, top: r.y, right: r.x + r.w, bottom: r.y + r.h, width: r.w, height: r.h, x: r.x, y: r.y, toJSON() {} }) as DOMRect;
}

beforeEach(() => {
  setPage('<button id="calc">Calculate</button><button id="cliff-btn">Check cliff edges</button><input type="password" id="pw" aria-label="Password"><input id="u" name="adults" aria-label="Adults">');
  Object.assign(window, { screenX: 100, screenY: 50, outerWidth: 1300, outerHeight: 900, innerWidth: 1280, innerHeight: 800, scrollX: 0, scrollY: 240, devicePixelRatio: 2 });
  layout(q("#calc"), { x: 412.5, y: 318, w: 96, h: 36 });
  layout(q("#cliff-btn"), { x: 20, y: 40, w: 150, h: 30 });
  layout(q("#pw"), { x: 20, y: 90, w: 150, h: 30 });
  layout(q("#u"), { x: 20, y: 140, w: 150, h: 30 });
});

describe("resolveRect", () => {
  const deps = { salt: SALT, matcher, now: () => 5000 };

  it("finds an element by salted label hash and answers geometry only", () => {
    const res = resolveRect(window, { request_id: "rq1", frame_id: "top", label_hash: hashLabel(SALT, "Calculate") }, deps);
    expect(res.found).toBe(true);
    expect(res.rect).toEqual({ x: 412.5, y: 318, w: 96, h: 36 });
    expect(res.scroll).toEqual({ x: 0, y: 240 });
    expect(res.dpr).toBe(2);
    // window offset: screen position plus browser chrome (outer minus inner height, less half the side border)
    expect(res.window_offset).toEqual({ x: 110, y: 50 + (900 - 800 - 10) });
    expect(JSON.stringify(res)).not.toContain("Calculate");
  });

  it("finds an element by role and name, case and spacing insensitive", () => {
    const res = resolveRect(window, { request_id: "rq2", frame_id: "top", role: "button", name: "  check CLIFF edges " }, deps);
    expect(res.found).toBe(true);
    expect(res.rect?.x).toBe(20);
  });

  it("answers found:false when nothing matches", () => {
    expect(resolveRect(window, { request_id: "rq3", frame_id: "top", label_hash: "h:000000000000" }, deps).found).toBe(false);
    expect(resolveRect(window, { request_id: "rq3", frame_id: "top", role: "button", name: "Nope" }, deps).found).toBe(false);
  });

  it("never returns a sensitive element, however it is asked for", () => {
    expect(resolveRect(window, { request_id: "rq4", frame_id: "top", label_hash: hashLabel(SALT, "Password") }, deps).found).toBe(false);
    expect(resolveRect(window, { request_id: "rq4", frame_id: "top", role: "textbox", name: "Password" }, deps).found).toBe(false);
  });

  it("skips elements with no size", () => {
    layout(q("#calc"), { x: 0, y: 0, w: 0, h: 0 });
    expect(resolveRect(window, { request_id: "rq5", frame_id: "top", role: "button", name: "Calculate" }, deps).found).toBe(false);
  });

  it("prefers an element inside the viewport when the name is not unique", () => {
    setPage('<button id="a">Go</button><button id="b">Go</button>');
    layout(q("#a"), { x: 0, y: 5000, w: 50, h: 20 });
    layout(q("#b"), { x: 10, y: 10, w: 50, h: 20 });
    const res = resolveRect(window, { request_id: "rq6", frame_id: "top", role: "button", name: "Go" }, deps);
    expect(res.rect?.y).toBe(10);
  });

  it("produces answers that validate against the shared protocol schema", () => {
    const r = resolveRect(window, { request_id: "rq1", frame_id: "top", label_hash: hashLabel(SALT, "Calculate") }, deps);
    const body = { request_id: "rq1", frame_id: "top", found: true, rect: r.rect, window_offset: r.window_offset, scroll: r.scroll, dpr: r.dpr, age_ms: 12 };
    expect(validate(body), JSON.stringify(validate.errors)).toBe(true);
    expect(validate({ request_id: "rq1", frame_id: "top", found: false, age_ms: 0 })).toBe(true);
  });
});
