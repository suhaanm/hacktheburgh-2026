// Element-rect protocol (packages/schema/ext_rect.schema.json). The desktop app asks for the rect of an
// element by salted label hash (the same hash as L0) or by role+name; the answer is geometry only.
// Sensitive elements are never returned.
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

export interface RectResult {
  found: boolean;
  rect?: { x: number; y: number; w: number; h: number };
  window_offset?: { x: number; y: number };
  scroll?: { x: number; y: number };
  dpr?: number;
  viewport?: { w: number; h: number };
  outer?: { w: number; h: number };
  screen?: { x: number; y: number };
  measured_at: number;
}

const MAX_CANDIDATES = 2500;

function inViewport(win: Window, r: DOMRect): boolean {
  return r.bottom > 0 && r.right > 0 && r.top < win.innerHeight && r.left < win.innerWidth;
}

export function resolveRect(win: Window, want: RectWant, deps: { salt: string; matcher: SensitiveMatcher; zoner?: Zoner; now?: () => number }): RectResult {
  const now = deps.now ?? (() => Date.now());
  const doc = win.document;
  if (want.zone !== undefined) return finish(win, zoneMatches(win, want.zone, deps), now);
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
  return finish(win, matches, now);
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

function finish(win: Window, matches: Element[], now: () => number): RectResult {
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
    measured_at: now(),
  };
}
