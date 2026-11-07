import { beforeEach, describe, expect, it } from "vitest";
import { resolveRect } from "../src/content/rect";
import { hashLabel } from "../src/shared/hash";
import { ajvFor, matcher, SALT, setPage, zonerFor } from "./helpers";

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

  it("reports the raw window geometry beside window_offset, so the desktop app can work out page zoom", () => {
    const res = resolveRect(window, { request_id: "rq1", frame_id: "top", label_hash: hashLabel(SALT, "Calculate") }, deps);
    expect(res.viewport).toEqual({ w: 1280, h: 800 });
    expect(res.outer).toEqual({ w: 1300, h: 900 });
    expect(res.screen).toEqual({ x: 100, y: 50 });
    const body = { request_id: "rq1", frame_id: "top", found: true, rect: res.rect, window_offset: res.window_offset, scroll: res.scroll, dpr: res.dpr, viewport: res.viewport, outer: res.outer, screen: res.screen, age_ms: 3 };
    expect(validate(body), JSON.stringify(validate.errors)).toBe(true);
  });
});

describe("resolveRect by zone", () => {
  const SITE = "127.0.0.1:7801";
  const deps = (host = SITE) => ({ salt: SALT, matcher, zoner: zonerFor(host), now: () => 5000 });
  beforeEach(() => {
    setPage('<input id="pw" type="password" aria-label="Password" data-understudy-zone="cliff_button"><form action="/step/1"><label for="age">Your age</label><input id="age" name="your_age"></form>' +
      '<p id="result-amount">£1</p><button id="cliff-btn">Check cliff edges</button><div id="cliff-panel" role="region"><li>x</li></div>');
    Object.assign(window, { screenX: 10, screenY: 20, outerWidth: 1000, outerHeight: 800, innerWidth: 1000, innerHeight: 700, scrollX: 0, scrollY: 0, devicePixelRatio: 2 });
    layout(q("#cliff-btn"), { x: 30, y: 400, w: 140, h: 32 });
    layout(q("#cliff-panel"), { x: 30, y: 440, w: 400, h: 120 });
    layout(q("form"), { x: 20, y: 50, w: 600, h: 100 });
    layout(q("#age"), { x: 30, y: 100, w: 120, h: 24 });
    layout(q("#pw"), { x: 30, y: 60, w: 120, h: 24 });
    layout(q("#result-amount"), { x: 30, y: 300, w: 60, h: 20 });
  });

  it("finds a zone by the site's configured selector", () => {
    const r = resolveRect(window, { request_id: "z1", frame_id: "top", zone: "cliff_button" }, deps());
    expect(r.found).toBe(true);
    expect(r.rect).toEqual({ x: 30, y: 400, w: 140, h: 32 });
    expect(resolveRect(window, { request_id: "z2", frame_id: "top", zone: "cliff_panel" }, deps()).rect?.y).toBe(440);
    expect(resolveRect(window, { request_id: "z3", frame_id: "top", zone: "household_form" }, deps()).found).toBe(true);
    expect(resolveRect(window, { request_id: "z4", frame_id: "top", zone: "calc_result" }, deps()).rect?.y).toBe(300);
  });

  it("finds a zone by the explicit attribute on an unconfigured site", () => {
    setPage('<div id="x" data-understudy-zone="cliff_panel">hello</div>');
    layout(q("#x"), { x: 5, y: 6, w: 70, h: 20 });
    expect(resolveRect(window, { request_id: "z5", frame_id: "top", zone: "cliff_panel" }, deps("example.org")).rect).toEqual({ x: 5, y: 6, w: 70, h: 20 });
  });

  it("never answers for a sensitive element, even one that claims the zone with the attribute", () => {
    // the password field carries data-understudy-zone="cliff_button" and sits first in the document
    const r = resolveRect(window, { request_id: "z6", frame_id: "top", zone: "cliff_button" }, deps());
    expect(r.rect?.y).toBe(400);                       // the real button, not the password field at y 60
    setPage('<input id="only" type="password" data-understudy-zone="cliff_button">');
    layout(q("#only"), { x: 1, y: 1, w: 50, h: 20 });
    expect(resolveRect(window, { request_id: "z7", frame_id: "top", zone: "cliff_button" }, deps()).found).toBe(false);
  });

  it("answers found:false for an unknown zone, a zone absent from the page, and a hidden element", () => {
    expect(resolveRect(window, { request_id: "z8", frame_id: "top", zone: "not_a_zone" }, deps()).found).toBe(false);
    expect(resolveRect(window, { request_id: "z9", frame_id: "top", zone: "case_note" }, deps()).found).toBe(false);
    layout(q("#cliff-btn"), { x: 0, y: 0, w: 0, h: 0 });
    expect(resolveRect(window, { request_id: "z10", frame_id: "top", zone: "cliff_button" }, deps()).found).toBe(false);
  });

  it("without a zoner (older caller) a zone request simply finds nothing", () => {
    expect(resolveRect(window, { request_id: "z11", frame_id: "top", zone: "cliff_button" }, { salt: SALT, matcher }).found).toBe(false);
  });

  it("label_hash and role+name still work beside zone", () => {
    expect(resolveRect(window, { request_id: "a", frame_id: "top", label_hash: hashLabel(SALT, "Check cliff edges") }, deps()).found).toBe(true);
    expect(resolveRect(window, { request_id: "b", frame_id: "top", role: "button", name: "check cliff edges" }, deps()).found).toBe(true);
  });
});
