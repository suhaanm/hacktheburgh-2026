// Element-rect protocol (packages/schema/ext_rect.schema.json). The desktop app asks for the rect of an
// element by salted label hash (the same hash as L0) or by role+name; the answer is geometry only.
// Sensitive elements are never returned.
import { accessibleName, INTERACTIVE_SELECTOR, isVisible, roleOf } from "../shared/dom";
import { hashLabel, normaliseLabel } from "../shared/hash";
import type { SensitiveMatcher } from "../shared/sensitive";

export interface RectWant {
  request_id: string;
  frame_id: string;
  label_hash?: string;
  role?: string;
  name?: string;
}

export interface RectResult {
  found: boolean;
  rect?: { x: number; y: number; w: number; h: number };
  window_offset?: { x: number; y: number };
  scroll?: { x: number; y: number };
  dpr?: number;
  measured_at: number;
}

const MAX_CANDIDATES = 2500;

function inViewport(win: Window, r: DOMRect): boolean {
  return r.bottom > 0 && r.right > 0 && r.top < win.innerHeight && r.left < win.innerWidth;
}

export function resolveRect(win: Window, want: RectWant, deps: { salt: string; matcher: SensitiveMatcher; now?: () => number }): RectResult {
  const now = deps.now ?? (() => Date.now());
  const doc = win.document;
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
    measured_at: now(),
  };
}
