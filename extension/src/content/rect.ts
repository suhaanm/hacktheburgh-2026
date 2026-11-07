// Element-rect protocol (packages/schema/ext_rect.schema.json). The desktop app asks for the rect of an
// element by salted label hash (the same hash as L0) or by role+name; the answer is geometry only.
// Sensitive elements are never returned. The answer also carries `content`: up to 80 anonymous boxes (one per visible text
// line and per visible control) on a 0..1000 grid, numbers only, so the overlay can see where the page has something on it.
import { accessibleName, INTERACTIVE_SELECTOR, isVisible, roleOf } from "../shared/dom";
import { hashLabel, normaliseLabel } from "../shared/hash";
import type { SensitiveMatcher } from "../shared/sensitive";
import type { Zoner } from "../shared/zones";

export interface RectWant {
  request_id: string;
  frame_id: string;
  label_hash?: string;
  role?: string;
  name?: string;
  zone?: string;
}

/**
 * One box of page content on the 0..1000 grid of the answered rect's viewport (the top window's inner width and height):
 * [y0, x0, y1, x1], integers, y0 <= y1 and x0 <= x1. Numbers only: nothing derived from the page's text or attributes.
 */
export type ContentBox = [number, number, number, number];

/** Most boxes one answer carries. */
export const CONTENT_MAX = 80;

export interface RectResult {
  found: boolean;
  rect?: { x: number; y: number; w: number; h: number };
  window_offset?: { x: number; y: number };
  scroll?: { x: number; y: number };
  dpr?: number;
  viewport?: { w: number; h: number };
  outer?: { w: number; h: number };
  screen?: { x: number; y: number };
  /** Present on a found answer: the visible text lines and controls, in reading order (empty when unknown or nothing is visible). */
  content?: ContentBox[];
  measured_at: number;
}

const MAX_CANDIDATES = 2500;

function inViewport(win: Window, r: DOMRect): boolean {
  return r.bottom > 0 && r.right > 0 && r.top < win.innerHeight && r.left < win.innerWidth;
}

export function resolveRect(win: Window, want: RectWant, deps: { salt: string; matcher: SensitiveMatcher; zoner?: Zoner; now?: () => number }): RectResult {
  const now = deps.now ?? (() => Date.now());
  const doc = win.document;
  if (want.zone !== undefined) return finish(win, zoneMatches(win, want.zone, deps), now, deps.matcher);
  const candidates = Array.from(doc.querySelectorAll(`${INTERACTIVE_SELECTOR}, h1, h2, h3, label, [data-understudy-zone]`)).slice(0, MAX_CANDIDATES);
  const wantName = want.name !== undefined ? normaliseLabel(want.name) : null;
  const matches: Element[] = [];
  for (const el of candidates) {
    if (deps.matcher.inSensitiveContext(el)) continue;
    if (want.label_hash) {
      const name = accessibleName(el);
      if (!name || hashLabel(deps.salt, name) !== want.label_hash) continue;
    } else if (want.role && wantName !== null) {
      if (roleOf(el) !== want.role || normaliseLabel(accessibleName(el)) !== wantName) continue;
    } else continue;
    if (isVisible(el)) matches.push(el);
  }
  return finish(win, matches, now, deps.matcher);
}

/** Elements in document order that carry the zone attribute or match the zone's configured selector, never a sensitive one. */
function zoneMatches(win: Window, zone: string, deps: { matcher: SensitiveMatcher; zoner?: Zoner }): Element[] {
  const sels = deps.zoner?.selectorsFor(zone) ?? [];
  if (!sels.length) return [];
  let found: Element[] = [];
  try {
    found = Array.from(win.document.querySelectorAll(sels.join(", ")));
  } catch {
    for (const sel of sels) {      // one bad selector in a pack must not hide the others
      try { found.push(...Array.from(win.document.querySelectorAll(sel))); } catch { /* skip it */ }
    }
  }
  return found.filter((el) => !deps.matcher.inSensitiveContext(el) && isVisible(el)).slice(0, MAX_CANDIDATES);
}

function finish(win: Window, matches: Element[], now: () => number, matcher: SensitiveMatcher): RectResult {
  if (!matches.length) return { found: false, measured_at: now() };
  const best = matches.find((el) => inViewport(win, el.getBoundingClientRect())) ?? matches[0]!;
  const r = best.getBoundingClientRect();

  // Same-origin frames: express the rect in the top window's viewport. A cross-origin frame stops the
  // chain; the answer's frame_id then tells the desktop app the rect is relative to that frame.
  let x = r.left;
  let y = r.top;
  let top: Window = win;
  try {
    while (top.frameElement && top.parent && top.parent !== top) {
      const fr = top.frameElement.getBoundingClientRect();
      x += fr.left + top.frameElement.clientLeft;
      y += fr.top + top.frameElement.clientTop;
      top = top.parent;
    }
  } catch {
    // cross-origin parent
  }
  const side = Math.max(0, (top.outerWidth - top.innerWidth) / 2);
  const chrome = Math.max(0, top.outerHeight - top.innerHeight - side);
  // The page's content, in the same frame as the rect: this window's viewport, shifted by the same frame offsets, on the top window's grid.
  const content = collectContent(win, matcher, { ox: x - r.left, oy: y - r.top, topW: top.innerWidth, topH: top.innerHeight });
  return {
    found: true,
    rect: { x, y, w: r.width, h: r.height },
    window_offset: { x: top.screenX + side, y: top.screenY + chrome },
    scroll: { x: top.scrollX, y: top.scrollY },
    dpr: top.devicePixelRatio || 1,
    // The raw window geometry, so the desktop app can work out the page zoom itself instead of trusting window_offset.
    viewport: { w: top.innerWidth, h: top.innerHeight },
    outer: { w: top.outerWidth, h: top.outerHeight },
    screen: { x: top.screenX, y: top.screenY },
    content,
    measured_at: now(),
  };
}

// ---------- content boxes ----------
// Only geometry leaves this file. The walk reads tag names, a few visibility attributes and computed styles to decide what is visible,
// and the L0 sensitive-field rules to decide which text lines to drop; it never keeps, returns or logs a string from the page.

/** A box in a window's viewport, CSS pixels. */
interface Box { x0: number; y0: number; x1: number; y1: number }

/** Never entered: not rendered as page content, or rendered by something else (a frame, a control). */
const SKIP_TAGS = new Set(["script", "style", "noscript", "template", "head", "title", "meta", "link", "iframe", "frame", "object", "embed", "audio", "datalist", "option", "optgroup", "map"]);
/** Controls that count as one box and whose insides (a button's label, an svg's text) are not read. */
const LEAF_CONTROLS = new Set(["input", "textarea", "select", "button", "img", "svg", "canvas", "video"]);
/** Elements visited in one answer (the page is huge or hostile: bound the work). */
const SCAN_BUDGET = 6000;

const finite = (n: number): boolean => Number.isFinite(n);

function collectContent(win: Window, matcher: SensitiveMatcher, geo: { ox: number; oy: number; topW: number; topH: number }): ContentBox[] {
  try {
    return collect(win, matcher, geo);
  } catch {
    return []; // a measuring problem must never cost the caller its answer
  }
}

function collect(win: Window, matcher: SensitiveMatcher, geo: { ox: number; oy: number; topW: number; topH: number }): ContentBox[] {
  const doc = win.document;
  const root = doc.body ?? doc.documentElement;
  const vw = win.innerWidth;
  const vh = win.innerHeight;
  if (!root || !(vw > 0) || !(vh > 0) || !(geo.topW > 0) || !(geo.topH > 0) || !finite(geo.ox) || !finite(geo.oy)) return [];

  const inView = (l: number, t: number, w: number, h: number): boolean => finite(l + t + w + h) && w > 0 && h > 0 && l + w > 0 && t + h > 0 && l < vw && t < vh;
  const controls: Box[] = [];
  const fragments: Box[] = [];
  const range = doc.createRange();
  const canMeasureText = typeof range.getClientRects === "function";

  // Is a text line here off limits? Same rule as the rect lookup: the element itself, or a form (or login-style container) that holds a sensitive control.
  const formSensitive = new Map<Element, boolean>();
  const sensitive = new Map<Element, boolean>();
  const isSensitive = (el: Element): boolean => {
    const known = sensitive.get(el);
    if (known !== undefined) return known;
    let v: boolean;
    try {
      const form = el.closest("form");
      if (form) {
        let f = formSensitive.get(form);
        if (f === undefined) { f = matcher.inSensitiveContext(form); formSensitive.set(form, f); }
        v = f || matcher.isSensitiveElement(el);
      } else v = matcher.inSensitiveContext(el);
    } catch {
      v = true; // fail closed
    }
    sensitive.set(el, v);
    return v;
  };

  const readText = (t: Text, parent: Element): void => {
    if (!canMeasureText || !/\S/.test(t.data) || isSensitive(parent)) return;
    range.selectNodeContents(t);
    const list = range.getClientRects();
    for (let i = 0; i < list.length; i++) {
      const q = list[i]!;
      if (inView(q.left, q.top, q.width, q.height)) fragments.push({ x0: q.left, y0: q.top, x1: q.left + q.width, y1: q.top + q.height });
    }
  };

  const stack: Element[] = [root];
  let budget = SCAN_BUDGET;
  while (stack.length && budget > 0) {
    const el = stack.pop()!;
    budget -= 1;
    const tag = el.localName;
    if (SKIP_TAGS.has(tag) || el.hasAttribute("hidden") || el.getAttribute("aria-hidden") === "true") continue;
    const cs = win.getComputedStyle(el);
    if (cs.display === "none") continue;
    const hiddenSelf = cs.visibility === "hidden" || cs.visibility === "collapse";
    const r = el.getBoundingClientRect();
    // A box that is plainly off screen takes everything inside it with it.
    if (r.width > 0 && r.height > 0 && !inView(r.left, r.top, r.width, r.height) && el !== root) continue;

    const control = LEAF_CONTROLS.has(tag) || (tag === "a" && el.hasAttribute("href"));
    // A sensitive control (a password or one-time-code field, anything on sensitive_fields.json, anything in a form that holds one) is NEVER
    // measured: no box, no size, no position (the same rule as the rect lookup above).
    if (control && !hiddenSelf && inView(r.left, r.top, r.width, r.height) && !isSensitive(el) && !(tag === "input" && ((el as HTMLInputElement).type || el.getAttribute("type") || "").toLowerCase() === "hidden")) {
      controls.push({ x0: r.left, y0: r.top, x1: r.left + r.width, y1: r.top + r.height });
    }
    if (LEAF_CONTROLS.has(tag)) continue;

    const kids = el.childNodes;
    const elems: Element[] = [];
    for (let i = 0; i < kids.length; i++) {
      const n = kids[i]!;
      if (n.nodeType === 3) {
        budget -= 1;
        if (!hiddenSelf) readText(n as Text, el);
      } else if (n.nodeType === 1) elems.push(n as Element);
    }
    for (let i = elems.length - 1; i >= 0; i--) stack.push(elems[i]!);
  }

  const raw: Box[] = [...controls, ...mergeLines(fragments)];
  const seen = new Set<string>();
  const boxes: Array<{ box: ContentBox; area: number }> = [];
  const norm = (v: number, extent: number): number => Math.round(Math.min(1000, Math.max(0, (v * 1000) / extent)));
  for (const b of raw) {
    // Only the part inside this window's viewport, then shifted into the top window's frame and onto its 0..1000 grid.
    const x0 = Math.max(0, b.x0), y0 = Math.max(0, b.y0), x1 = Math.min(vw, b.x1), y1 = Math.min(vh, b.y1);
    if (!(x1 > x0 && y1 > y0)) continue;
    const box: ContentBox = [norm(y0 + geo.oy, geo.topH), norm(x0 + geo.ox, geo.topW), norm(y1 + geo.oy, geo.topH), norm(x1 + geo.ox, geo.topW)];
    if (box[2] <= box[0] || box[3] <= box[1]) continue; // nothing left once rounded or clamped
    const key = box.join(",");
    if (seen.has(key)) continue;
    seen.add(key);
    boxes.push({ box, area: (box[2] - box[0]) * (box[3] - box[1]) });
  }
  const reading = (a: ContentBox, b: ContentBox): number => a[0] - b[0] || a[1] - b[1] || a[2] - b[2] || a[3] - b[3];
  const kept = boxes.length > CONTENT_MAX ? boxes.sort((a, b) => b.area - a.area || reading(a.box, b.box)).slice(0, CONTENT_MAX) : boxes;
  return kept.map((k) => k.box).sort(reading);
}

/**
 * Text fragments (one per line of one text node) into one tight box per line. Fragments that share a similar top and height are one
 * row; within a row, fragments that sit about a word apart or closer are one line, so a second column or a far-away table cell stays
 * a box of its own.
 */
function mergeLines(fragments: Box[]): Box[] {
  const sorted = [...fragments].sort((a, b) => a.y0 - b.y0 || a.x0 - b.x0);
  type Row = { box: Box; parts: Box[] };
  const rows: Row[] = [];
  let active: Row[] = [];
  for (const f of sorted) {
    active = active.filter((row) => row.box.y1 >= f.y0); // a row entirely above this fragment is above every later one too: closed
    const fh = f.y1 - f.y0;
    const row = active.find((r) => {
      const rh = r.box.y1 - r.box.y0;
      const small = Math.min(rh, fh);
      return small / Math.max(rh, fh) >= 0.6 && Math.abs(r.box.y0 - f.y0) <= 0.35 * small;
    });
    if (row) {
      row.parts.push(f);
      row.box = { x0: Math.min(row.box.x0, f.x0), y0: Math.min(row.box.y0, f.y0), x1: Math.max(row.box.x1, f.x1), y1: Math.max(row.box.y1, f.y1) };
    } else {
      const fresh = { box: { ...f }, parts: [f] };
      rows.push(fresh);
      active.push(fresh);
    }
  }
  const lines: Box[] = [];
  for (const row of rows) {
    let cur: Box | null = null;
    for (const f of row.parts.sort((a, b) => a.x0 - b.x0)) {
      if (cur && f.x0 - cur.x1 <= 1.5 * Math.max(cur.y1 - cur.y0, f.y1 - f.y0)) {
        cur.x1 = Math.max(cur.x1, f.x1);
        cur.y0 = Math.min(cur.y0, f.y0);
        cur.y1 = Math.max(cur.y1, f.y1);
      } else {
        if (cur) lines.push(cur);
        cur = { ...f };
      }
    }
    if (cur) lines.push(cur);
  }
  return lines;
}
