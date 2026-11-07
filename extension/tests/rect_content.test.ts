// The optional `content` field of the element-rect answer: one box per visible text line and per visible control, numbers only,
// on the 0..1000 grid of the answered rect's viewport. jsdom has no layout, so every box is mocked, as in rect.test.ts.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanContent, RectPoller } from "../src/background/rect_poller";
import { CONTENT_MAX, resolveRect, type ContentBox, type RectWant } from "../src/content/rect";
import { ajvFor, matcher, SALT, setPage, zonerFor } from "./helpers";

type R = { x: number; y: number; w: number; h: number };
const domRect = (r: R) => ({ left: r.x, top: r.y, right: r.x + r.w, bottom: r.y + r.h, width: r.w, height: r.h, x: r.x, y: r.y, toJSON() {} }) as DOMRect;
const layout = (el: Element, r: R) => void ((el as HTMLElement).getBoundingClientRect = () => domRect(r));
const q = (s: string, root: ParentNode = document) => root.querySelector(s) as HTMLElement;

/** The mocked line boxes of each text node (what Range.getClientRects would report). */
const lineBoxes = new Map<Node, R[]>();
function textNodesOf(el: Element): Text[] {
  const w = el.ownerDocument.createTreeWalker(el, 4 /* SHOW_TEXT */);
  const out: Text[] = [];
  for (let n = w.nextNode(); n; n = w.nextNode()) out.push(n as Text);
  return out;
}
/** Give the text nodes of `el`, in tree order, their line boxes. */
const lines = (el: Element, ...perNode: R[][]) => textNodesOf(el).forEach((n, i) => lineBoxes.set(n, perNode[i] ?? []));

const saved = new Map<object, PropertyDescriptor | undefined>();
function mockRange(w: Window): void {
  const proto = (w as unknown as { Range: { prototype: object } }).Range.prototype;
  saved.set(proto, Object.getOwnPropertyDescriptor(proto, "getClientRects"));
  Object.defineProperty(proto, "getClientRects", {
    configurable: true,
    writable: true,
    value(this: Range) {
      return (lineBoxes.get(this.startContainer) ?? []).map(domRect);
    },
  });
}

beforeEach(() => {
  Object.assign(window, { screenX: 0, screenY: 0, outerWidth: 1000, outerHeight: 600, innerWidth: 1000, innerHeight: 500, scrollX: 0, scrollY: 0, devicePixelRatio: 1 });
  mockRange(window);
});
afterEach(() => {
  for (const [proto, d] of saved) {
    if (d) Object.defineProperty(proto, "getClientRects", d);
    else delete (proto as { getClientRects?: unknown }).getClientRects;
  }
  saved.clear();
  lineBoxes.clear();
});

const deps = { salt: SALT, matcher, now: () => 5000 };
const GO: RectWant = { request_id: "rq1", frame_id: "top", role: "button", name: "Go" };
const GO_RECT: R = { x: 100, y: 50, w: 200, h: 100 };   // grid: [100, 100, 300, 300] on a 1000 x 500 viewport
const GO_BOX: ContentBox = [100, 100, 300, 300];
const content = (w: Window = window) => resolveRect(w, GO, deps).content!;
/** The page with the target button, laid out. */
function page(html: string): void {
  setPage(`<button id="go">Go</button>${html}`);
  layout(q("#go"), GO_RECT);
}
const reading = (a: ContentBox, b: ContentBox) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2] || a[3] - b[3];

describe("content: the count cap", () => {
  function manyLines(n: number, buttons = 0): void {
    page(Array.from({ length: n }, (_, i) => `<p id="l${i}">line number ${i}</p>`).join("") + Array.from({ length: buttons }, (_, i) => `<button id="b${i}">Button ${i}</button>`).join(""));
    for (let i = 0; i < n; i++) lines(q(`#l${i}`), [{ x: (i % 4) * 250 + 5, y: Math.floor(i / 4) * 9, w: 200, h: 8 }]);   // 4 columns of 50 rows, all distinct and inside
    for (let i = 0; i < buttons; i++) layout(q(`#b${i}`), { x: (i % 6) * 160 + 3, y: 100 + Math.floor(i / 6) * 50, w: 100, h: 40 });
  }

  it("a page with 200 text lines and 30 controls yields exactly 80 boxes, in reading order, all integers on the grid", () => {
    manyLines(200, 30);
    const c = content();
    expect(c).toHaveLength(80);
    expect(c).toHaveLength(CONTENT_MAX);
    for (const b of c) {
      expect(b).toHaveLength(4);
      for (const n of b) { expect(Number.isInteger(n)).toBe(true); expect(n).toBeGreaterThanOrEqual(0); expect(n).toBeLessThanOrEqual(1000); }
      expect(b[0]).toBeLessThanOrEqual(b[2]);
      expect(b[1]).toBeLessThanOrEqual(b[3]);
    }
    expect([...c].sort(reading)).toEqual(c);
  });

  it("when there are more than 80, the largest by area are the ones kept (all 31 controls beat the small text lines)", () => {
    manyLines(200, 30);
    const c = content();
    const controlBoxes: ContentBox[] = [GO_BOX];
    for (let i = 0; i < 30; i++) {
      const x = (i % 6) * 160 + 3, y = 100 + Math.floor(i / 6) * 50;
      controlBoxes.push([Math.round(y * 2), Math.round(x), Math.round((y + 40) * 2), Math.round(x + 100)]);
    }
    for (const b of controlBoxes) expect(c).toContainEqual(b);
    // the other 49 are text lines, each 200 x 8 px: 200 x 16 units
    expect(c.filter((b) => b[3] - b[1] === 200 && b[2] - b[0] === 16)).toHaveLength(49);
  });

  it("exactly at the cap and just under it nothing is lost, one over is cut to 80", () => {
    manyLines(79);
    expect(content()).toHaveLength(80);   // 79 lines + the target button
    manyLines(78);
    expect(content()).toHaveLength(79);
    manyLines(100);
    expect(content()).toHaveLength(80);
  });
});

describe("content: no text leaves the page", () => {
  const CANARIES = ["zqxText", "zqxValue", "zqxAria", "zqxAlt", "zqxTitle", "zqxHref", "zqxId", "zqxClass", "zqxName", "zqxPlaceholder", "zqxData", "zqxOption", "zqxArea", "zqxSvg"];

  function leakyPage(): void {
    page(
      `<h1 id="zqxId-h" class="zqxClass-h" title="zqxTitle">zqxText heading</h1>` +
      `<p id="zqxId-p" class="zqxClass-p" data-note="zqxData" title="zqxTitle">zqxText paragraph with <a id="zqxId-a" class="zqxClass-a" href="https://example.test/zqxHref" aria-label="zqxAria" title="zqxTitle">zqxText link</a> inside</p>` +
      `<img id="zqxId-i" class="zqxClass-i" alt="zqxAlt" title="zqxTitle" src="data:,zqxHref">` +
      `<input id="zqxId-in" class="zqxClass-in" name="zqxName" value="zqxValue" placeholder="zqxPlaceholder" aria-label="zqxAria" title="zqxTitle">` +
      `<textarea id="zqxId-ta" name="zqxName" aria-label="zqxAria">zqxArea</textarea>` +
      `<select id="zqxId-s" name="zqxName" aria-label="zqxAria"><option value="zqxValue">zqxOption</option></select>` +
      `<button id="zqxId-b" class="zqxClass-b" aria-label="zqxAria" title="zqxTitle">zqxText button</button>` +
      `<svg id="zqxId-svg" aria-label="zqxAria"><title>zqxSvg</title><text>zqxSvg</text></svg>` +
      `<canvas id="zqxId-c" aria-label="zqxAria">zqxText</canvas><video id="zqxId-v" src="zqxHref" title="zqxTitle"></video>`,
    );
    (document.querySelector("#zqxId-in") as HTMLInputElement).value = "zqxValue";
    let y = 160;
    for (const id of ["zqxId-h", "zqxId-p", "zqxId-a", "zqxId-i", "zqxId-in", "zqxId-ta", "zqxId-s", "zqxId-b", "zqxId-svg", "zqxId-c", "zqxId-v"]) {
      layout(q(`#${id}`), { x: 20, y, w: 300, h: 20 });
      y += 25;
    }
    lines(q("#zqxId-h"), [{ x: 20, y: 160, w: 120, h: 18 }]);
    lines(q("#zqxId-p"), [{ x: 20, y: 185, w: 100, h: 18 }], [{ x: 122, y: 185, w: 60, h: 18 }], [{ x: 184, y: 185, w: 40, h: 18 }]);
  }

  async function answerBody(): Promise<Record<string, unknown>> {
    const posts: Array<Record<string, unknown>> = [];
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === "POST") { posts.push(JSON.parse(init.body as string)); return new Response("{}", { status: 200 }); }
      return new Response(JSON.stringify(GO), { status: 200 });
    });
    const poller = new RectPoller({
      fetch: fetchMock as unknown as typeof fetch,
      getDesktopUrl: async () => "http://127.0.0.1:7720",
      resolve: async (want) => ({ ...resolveRect(window, want, deps), frame_id: "top" }),
      now: () => 5100,
    });
    await poller.tick();
    return posts[0]!;
  }

  it("no canary planted in text, values, aria-label, alt, title, href, id, class or name appears anywhere in the posted answer", async () => {
    leakyPage();
    const body = await answerBody();
    const c = body.content as unknown[];
    expect(c.length).toBeGreaterThan(8);   // the controls and the lines were really measured: this is not a vacuous check
    const json = JSON.stringify(body);
    for (const canary of CANARIES) expect(json, canary).not.toContain(canary);
    expect(json).not.toMatch(/zqx/i);
    for (const k of Object.keys(body)) expect(["request_id", "frame_id", "found", "rect", "window_offset", "scroll", "dpr", "viewport", "outer", "screen", "content", "age_ms"]).toContain(k);
  });

  it("content is nothing but arrays of four numbers: no string at all inside it", async () => {
    leakyPage();
    const body = await answerBody();
    expect(JSON.stringify(body.content)).toMatch(/^\[(\[\d+,\d+,\d+,\d+\],?)+\]$/);
    for (const box of body.content as unknown[]) {
      expect(Array.isArray(box)).toBe(true);
      expect((box as unknown[]).every((n) => typeof n === "number")).toBe(true);
    }
    // the answer validates against the shared schema
    const validate = ajvFor("ext_rect.schema.json");
    expect(validate(body), JSON.stringify(validate.errors)).toBe(true);
  });

  it("even the raw result of the content script holds numbers only in content", () => {
    leakyPage();
    const res = resolveRect(window, GO, deps);
    expect(JSON.stringify(res.content)).not.toMatch(/[A-Za-z"]/);
  });

  it("the poller drops anything that is not a box of four finite numbers, so a string cannot ride along", () => {
    const dirty: unknown[] = [[1, 2, 3, 4], "zqxText", ["a", 1, 2, 3], [1, 2, 3], [1, 2, 3, 4, 5], [1, 2, 3, NaN], [1, 2, 3, Infinity], { 0: 1, 1: 2, 2: 3, 3: 4, length: 4 }, null, [9, 9, 3, 4], [1, 9, 3, 4 - 5], [-5, 0, 5000, 2000], [1.4, 2.6, 3, 4.5], [1, "2", 3, 4]];
    expect(cleanContent(dirty)).toEqual([[1, 2, 3, 4], [0, 0, 1000, 1000], [1, 3, 3, 5]]);
    expect(cleanContent("zqxText")).toEqual([]);
    expect(cleanContent(undefined)).toEqual([]);
    expect(cleanContent(Array.from({ length: 200 }, () => [1, 1, 2, 2]))).toHaveLength(80);
  });
});

describe("content: coordinates", () => {
  it("maps a known layout onto the 0..1000 grid of the viewport, clamped and rounded, in reading order", () => {
    // viewport 1000 x 500: one x pixel is one unit, one y pixel is two units
    page(
      `<p id="p1">Alpha</p><p id="p2">Beta</p><p id="p3">Gamma</p><a id="lk" href="#x">link</a><img id="im" alt="x" src="x.png">`,
    );
    lines(q("#p1"), [{ x: 500, y: 250, w: 250, h: 25 }]);
    lines(q("#p2"), [{ x: 20, y: 250, w: 100, h: 25 }]);               // same top as p1, further left: reads first
    lines(q("#p3"), [{ x: 333.3, y: 101.1, w: 10.4, h: 7.7 }]);        // 202.2, 333.3, 217.6, 343.7 -> rounded
    layout(q("#lk"), { x: -50, y: 450, w: 200, h: 100 });              // sticks out left and below: clamped to the viewport
    layout(q("#im"), { x: 900, y: 10, w: 200, h: 20 });                // sticks out right
    expect(content()).toEqual([
      [20, 900, 60, 1000],      // image
      [100, 100, 300, 300],     // the target button
      [202, 333, 218, 344],     // Gamma
      [500, 20, 550, 120],      // Beta
      [500, 500, 550, 750],     // Alpha
      [900, 0, 1000, 150],      // link
    ]);
  });

  it("a different viewport size changes the grid, not the layout in pixels", () => {
    Object.assign(window, { innerWidth: 500, innerHeight: 1000 });
    page(`<p id="p">Text</p>`);
    lines(q("#p"), [{ x: 50, y: 100, w: 100, h: 50 }]);
    // x: 50 / 500 * 1000 = 100 .. 300 ; y: 100 / 1000 * 1000 = 100 .. 150
    expect(content()).toContainEqual([100, 100, 150, 300]);
    expect(content()).toContainEqual([50, 200, 150, 600]);   // the button at (100,50) 200 x 100
  });

  it("merges the fragments of one line into a tight box, but keeps another column, another line and a far-away cell apart", () => {
    page(`<p id="m">Hello <b>big</b> world, and then it wraps onto a second line</p><p id="far">Far</p>`);
    lines(q("#m"),
      [{ x: 10, y: 300, w: 50, h: 20 }],                                          // "Hello "
      [{ x: 62, y: 301, w: 30, h: 20 }],                                          // "big": same line, a hair lower, adjacent
      [{ x: 94, y: 300, w: 150, h: 20 }, { x: 10, y: 330, w: 80, h: 20 }]);       // " world ..." then the wrapped second line
    lines(q("#far"), [{ x: 700, y: 300, w: 50, h: 20 }]);                         // same row, 456 px away: a different box
    const c = content();
    expect(c).toContainEqual([600, 10, 642, 244]);    // y 300 .. 321 -> 600 .. 642, x 10 .. 244
    expect(c).toContainEqual([660, 10, 700, 90]);
    expect(c).toContainEqual([600, 700, 640, 750]);
    expect(c).toHaveLength(4);                       // those three and the button
  });

  it("works for a zone request as well (same measuring path)", () => {
    setPage(`<button id="cliff-btn">Check cliff edges</button><p id="t">Some text</p>`);
    layout(q("#cliff-btn"), { x: 30, y: 400, w: 140, h: 32 });
    lines(q("#t"), [{ x: 30, y: 10, w: 100, h: 20 }]);
    const res = resolveRect(window, { request_id: "z1", frame_id: "top", zone: "cliff_button" }, { salt: SALT, matcher, zoner: zonerFor("127.0.0.1:7801"), now: () => 1 });
    expect(res.found).toBe(true);
    expect(res.content).toEqual([[20, 30, 60, 130], [800, 30, 864, 170]]);
  });

  it("is an empty array, not missing, when the page has nothing else visible, and absent when nothing was found", () => {
    setPage(`<button id="go" style="display:block">Go</button>`);
    layout(q("#go"), { x: 0, y: 0, w: 0, h: 0 });   // not visible: not found
    const none = resolveRect(window, GO, deps);
    expect(none.found).toBe(false);
    expect(none).not.toHaveProperty("content");
    page("");
    layout(q("#go"), GO_RECT);
    expect(resolveRect(window, GO, deps).content).toEqual([GO_BOX]);
    Object.assign(window, { innerWidth: 0, innerHeight: 0 });
    expect(resolveRect(window, GO, deps).content).toEqual([]);   // the viewport is unknown: nothing to put on a grid
  });

  it("an unreadable layout API costs the answer nothing: content is empty and the rect is still there", () => {
    page(`<p id="p">Text</p>`);
    lines(q("#p"), [{ x: 1, y: 1, w: 10, h: 10 }]);
    const proto = Object.getPrototypeOf(document.createRange());
    Object.defineProperty(proto, "getClientRects", { configurable: true, writable: true, value() { throw new Error("boom"); } });
    const res = resolveRect(window, GO, deps);
    expect(res.found).toBe(true);
    expect(res.rect).toEqual(GO_RECT);
    expect(res.content).toEqual([]);
  });
});

describe("content: what is not visible is not there", () => {
  it("leaves out offscreen, display:none, visibility:hidden, hidden, aria-hidden, zero-size, script, style and hidden-input content", () => {
    page(
      `<p id="ok">visible</p>` +
      `<p id="ariaFalse" aria-hidden="false">visible too</p>` +
      `<p id="below">below</p><p id="above">above</p><p id="right">right</p><p id="left">left</p>` +
      `<p id="none" style="display:none">none</p>` +
      `<p id="vis" style="visibility:hidden">invisible</p>` +
      `<p id="hid" hidden>hidden</p>` +
      `<div id="aria" aria-hidden="true"><p id="ariaP">inside</p><button id="ariaB">x</button><a id="ariaA" href="#a">y</a></div>` +
      `<div id="nonePar" style="display:none"><p id="noneKid">kid</p><input id="noneIn"></div>` +
      `<p id="zero">zero</p>` +
      `<button id="zeroB">zero</button>` +
      `<script id="scr">var secretCode = 1;</script><style id="sty">.a { color: red }</style><noscript id="nos">no script</noscript><template id="tpl"><p>tpl</p></template>` +
      `<input id="hiddenIn" type="hidden" value="v">` +
      `<input id="ok-in" aria-label="Adults">` +
      `<a id="plain">anchor without href</a>` +
      `<div id="vhPar" style="visibility:hidden"><button id="vhB">hidden button</button><p id="vhKid" style="visibility:visible">shown child</p></div>`,
    );
    const at = (id: string, r: R) => { layout(q(`#${id}`), r); };
    lines(q("#ok"), [{ x: 10, y: 200, w: 100, h: 20 }]);
    lines(q("#ariaFalse"), [{ x: 10, y: 230, w: 100, h: 20 }]);
    lines(q("#below"), [{ x: 10, y: 600, w: 100, h: 20 }]);
    lines(q("#above"), [{ x: 10, y: -100, w: 100, h: 20 }]);
    lines(q("#right"), [{ x: 1200, y: 100, w: 100, h: 20 }]);
    lines(q("#left"), [{ x: -300, y: 100, w: 100, h: 20 }]);
    lines(q("#none"), [{ x: 10, y: 260, w: 100, h: 20 }]);
    lines(q("#vis"), [{ x: 10, y: 290, w: 100, h: 20 }]);
    lines(q("#hid"), [{ x: 10, y: 320, w: 100, h: 20 }]);
    lines(q("#ariaP"), [{ x: 10, y: 350, w: 100, h: 20 }]);
    lines(q("#noneKid"), [{ x: 10, y: 380, w: 100, h: 20 }]);
    lines(q("#zero"), [{ x: 10, y: 410, w: 0, h: 0 }, { x: 10, y: 410, w: 50, h: 0 }]);
    lines(q("#scr"), [{ x: 10, y: 440, w: 100, h: 20 }]);
    lines(q("#sty"), [{ x: 10, y: 440, w: 100, h: 20 }]);
    lines(q("#nos"), [{ x: 10, y: 440, w: 100, h: 20 }]);
    lines(q("#vhKid"), [{ x: 10, y: 470, w: 100, h: 20 }]);
    lines(q("#plain"), []);
    at("ariaB", { x: 200, y: 200, w: 50, h: 20 });
    at("ariaA", { x: 200, y: 230, w: 50, h: 20 });
    at("noneIn", { x: 200, y: 260, w: 50, h: 20 });
    at("zeroB", { x: 200, y: 290, w: 0, h: 20 });
    at("hiddenIn", { x: 200, y: 320, w: 50, h: 20 });
    at("ok-in", { x: 200, y: 350, w: 50, h: 20 });
    at("plain", { x: 200, y: 380, w: 50, h: 20 });
    at("vhB", { x: 200, y: 410, w: 50, h: 20 });
    at("below", { x: 0, y: 600, w: 100, h: 20 });     // the box of an offscreen element prunes what is inside it
    at("above", { x: 0, y: -100, w: 100, h: 20 });
    at("right", { x: 1200, y: 100, w: 100, h: 20 });
    at("left", { x: -300, y: 100, w: 100, h: 20 });

    expect(content()).toEqual([
      [100, 100, 300, 300],    // the target button
      [400, 10, 440, 110],     // "visible"
      [460, 10, 500, 110],     // aria-hidden="false" is not hidden
      [700, 200, 740, 250],    // the labelled input
      [940, 10, 980, 110],     // the visible child of a visibility:hidden parent
    ]);
  });

  it("controls partly or wholly outside the viewport", () => {
    page(
      `<input id="a" aria-label="a"><input id="b" aria-label="b"><input id="c" aria-label="c"><input id="d" aria-label="d"><input id="e" aria-label="e">`,
    );
    layout(q("#a"), { x: 10, y: -5, w: 100, h: 20 });      // top edge: keeps the visible 15 px
    layout(q("#b"), { x: 10, y: 495, w: 100, h: 20 });     // bottom edge: keeps 5 px
    layout(q("#c"), { x: 10, y: 500, w: 100, h: 20 });     // just below
    layout(q("#d"), { x: 1000, y: 10, w: 100, h: 20 });    // just right
    layout(q("#e"), { x: -100, y: 10, w: 100, h: 20 });    // just left
    expect(content()).toEqual([[0, 10, 30, 110], GO_BOX, [990, 10, 1000, 110]]);
  });
});

describe("content: sensitive fields", () => {
  it("never includes the text lines of a form with a password field, a sensitive label, or a one-time-code container; a plain text line stays", () => {
    page(
      `<form id="f"><label id="lb" for="pw">Password</label><input id="pw" type="password" value="zqxValue"><p id="note">Enter zqxText here</p><button id="sub" type="submit">Sign in</button></form>` +
      `<label id="ni" for="nino">National Insurance number</label><input id="nino" name="ni_number">` +
      `<div id="otpBox"><input id="otp" autocomplete="one-time-code"><span id="hint">zqxText hint</span></div>` +
      `<p id="plain">An ordinary paragraph</p>`,
    );
    layout(q("#pw"), { x: 20, y: 200, w: 200, h: 24 });
    layout(q("#sub"), { x: 20, y: 240, w: 80, h: 24 });
    layout(q("#nino"), { x: 20, y: 300, w: 200, h: 24 });
    layout(q("#otp"), { x: 20, y: 340, w: 200, h: 24 });
    lines(q("#lb"), [{ x: 20, y: 180, w: 80, h: 18 }]);
    lines(q("#note"), [{ x: 20, y: 220, w: 160, h: 18 }]);
    lines(q("#sub"), [{ x: 30, y: 244, w: 60, h: 16 }]);
    lines(q("#ni"), [{ x: 20, y: 280, w: 200, h: 18 }]);
    lines(q("#hint"), [{ x: 230, y: 345, w: 100, h: 18 }]);
    lines(q("#plain"), [{ x: 20, y: 400, w: 180, h: 18 }]);
    // every control is there as a plain box, and so is the plain line; no line of the form, the label or the container is
    expect(content()).toEqual([
      GO_BOX,
      [400, 20, 448, 220],   // the password field: a box, nothing else
      [480, 20, 528, 100],   // the submit button
      [600, 20, 648, 220],   // the NI number field
      [680, 20, 728, 220],   // the one-time-code field
      [800, 20, 836, 200],   // "An ordinary paragraph"
    ]);
  });
});

describe("content: same-origin frames share the answered rect's frame", () => {
  it("boxes found inside a frame are shifted by the frame's offset and put on the top window's grid", () => {
    setPage(`<iframe id="fr" src="about:blank"></iframe>`);
    const fr = q("#fr") as HTMLIFrameElement;
    layout(fr, { x: 100, y: 200, w: 300, h: 200 });
    const fw = fr.contentWindow!;
    mockRange(fw);
    Object.assign(fw, { innerWidth: 300, innerHeight: 200 });
    fr.contentDocument!.body.innerHTML = `<button id="go">Go</button><p id="in">inside</p><p id="out">outside the frame's own viewport</p>`;
    const inner = (s: string) => fr.contentDocument!.querySelector(s) as HTMLElement;
    layout(inner("#go"), { x: 10, y: 20, w: 50, h: 30 });
    lines(inner("#in"), [{ x: 10, y: 60, w: 100, h: 20 }]);
    lines(inner("#out"), [{ x: 10, y: 300, w: 100, h: 20 }]);   // below the frame's viewport although inside the top one
    const res = resolveRect(fw, GO, deps);
    expect(res.found).toBe(true);
    expect(res.rect).toEqual({ x: 110, y: 220, w: 50, h: 30 });
    // top viewport 1000 x 500: x 110..160 -> 110..160; y 220..250 -> 440..500
    expect(res.content).toEqual([[440, 110, 500, 160], [520, 110, 560, 210]]);
  });
});

describe("RectPoller carries content into the answer", () => {
  const found = { found: true, rect: { x: 1, y: 2, w: 3, h: 4 }, window_offset: { x: 0, y: 87 }, scroll: { x: 0, y: 0 }, dpr: 2, viewport: { w: 1000, h: 500 }, measured_at: 900, frame_id: "top" };
  async function run(result: object) {
    const posts: Array<Record<string, unknown>> = [];
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === "POST") { posts.push(JSON.parse(init.body as string)); return new Response("{}", { status: 200 }); }
      return new Response(JSON.stringify({ request_id: "rq1", label_hash: "h:9f2c", frame_id: "top" }), { status: 200 });
    });
    const p = new RectPoller({ fetch: fetchMock as unknown as typeof fetch, getDesktopUrl: async () => "http://127.0.0.1:7720", resolve: async () => result as never, now: () => 1000 });
    await p.tick();
    return posts[0]!;
  }
  const validate = ajvFor("ext_rect.schema.json");

  it("sends content as found, validates against the schema, and sends an empty array when the result has none", async () => {
    const withContent = await run({ ...found, content: [[100, 100, 300, 300], [500, 20, 550, 120]] });
    expect(withContent.content).toEqual([[100, 100, 300, 300], [500, 20, 550, 120]]);
    expect(validate(withContent), JSON.stringify(validate.errors)).toBe(true);
    const without = await run(found);
    expect(without.content).toEqual([]);
    expect(validate(without), JSON.stringify(validate.errors)).toBe(true);
  });

  it("sends no content on a found:false answer", async () => {
    const body = await run({ found: false, measured_at: 1 });
    expect(body).toEqual({ request_id: "rq1", frame_id: "top", found: false, age_ms: 0 });
  });
});

describe("ext_rect.schema.json: content", () => {
  const validate = ajvFor("ext_rect.schema.json");
  const base = { request_id: "rq1", frame_id: "top", found: true, rect: { x: 1, y: 2, w: 3, h: 4 }, window_offset: { x: 0, y: 0 }, scroll: { x: 0, y: 0 }, dpr: 1, age_ms: 3 };
  const box = (n: number) => [n % 1000, 0, (n % 1000) + 1 > 1000 ? 1000 : (n % 1000) + 1, 10];

  it("accepts valid content, an empty array and an answer without content", () => {
    expect(validate({ ...base, content: [[100, 100, 300, 300], [0, 0, 1000, 1000]] }), JSON.stringify(validate.errors)).toBe(true);
    expect(validate({ ...base, content: [] })).toBe(true);
    expect(validate(base)).toBe(true);
    expect(validate({ ...base, content: Array.from({ length: 80 }, (_, i) => box(i)) }), JSON.stringify(validate.errors)).toBe(true);
  });

  it("rejects 81 rects, rects of three numbers, string entries and anything else off the grid", () => {
    expect(validate({ ...base, content: Array.from({ length: 81 }, (_, i) => box(i)) })).toBe(false);
    expect(validate({ ...base, content: [[1, 2, 3]] })).toBe(false);
    expect(validate({ ...base, content: [[1, 2, 3, 4, 5]] })).toBe(false);
    expect(validate({ ...base, content: ["a heading"] })).toBe(false);
    expect(validate({ ...base, content: [["1", 2, 3, 4]] })).toBe(false);
    expect(validate({ ...base, content: [[1.5, 2, 3, 4]] })).toBe(false);
    expect(validate({ ...base, content: [[-1, 2, 3, 4]] })).toBe(false);
    expect(validate({ ...base, content: [[1, 2, 3, 1001]] })).toBe(false);
    expect(validate({ ...base, content: "text" })).toBe(false);
    expect(validate({ ...base, content: [null] })).toBe(false);
  });
});
