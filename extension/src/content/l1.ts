// L1 recording: only for a routine the worker opted in (the worker tells us through `active`). Records
// step-DSL drafts: selectors and field names, with every value replaced by a parameter slot. Values are
// never read. Fields on the sensitive list are skipped entirely. The recording has no conditions: the
// compile step adds preconditions and postconditions and dry-runs the bundle.
import { accessibleName, isFormField, roleOf } from "../shared/dom";
import type { SensitiveMatcher } from "../shared/sensitive";
import type { RecordedStep } from "../shared/types";

export interface L1Deps {
  win: Window & typeof globalThis;
  matcher: SensitiveMatcher;
  emit: (step: RecordedStep) => void;
  active: () => boolean;
  onSkipped?: () => void;
  now?: () => number;
  requireTrusted?: boolean;
  isTop?: boolean;
}

export function cssEscape(s: string): string {
  return s.replace(/^[0-9]/, (d) => `\\3${d} `).replace(/[^a-zA-Z0-9_-]/g, (c) => `\\${c}`);
}

function attrEscape(s: string): string {
  return s.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

const ID_SEGMENT = /^(\d+|[0-9a-f]{8,}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i;

/** Path with id-like segments replaced by `_id_`, no query, no hash, only DSL-safe characters. */
export function templatePath(pathname: string): string {
  const segs = pathname.split("/").map((seg) => {
    if (!seg) return seg;
    const hasDigit = /\d/.test(seg);
    const hasLetter = /[a-z]/i.test(seg);
    if (ID_SEGMENT.test(seg) || (hasDigit && hasLetter && seg.length >= 6)) return "_id_";
    return seg.replace(/[^A-Za-z0-9._-]/g, "_");
  });
  const out = segs.join("/");
  return out.startsWith("/") ? out : `/${out}`;
}

export function slotName(base: string, used: Set<string>): string {
  let s = base.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 28);
  if (!s) s = "field";
  if (!/^[a-z]/.test(s)) s = `p_${s}`;
  let out = s;
  for (let i = 2; used.has(out); i++) out = `${s}_${i}`.slice(0, 31);
  used.add(out);
  return out;
}

type Locator = { selector: string } | { role: string; name: string };

export function locate(el: Element): Locator {
  const doc = el.ownerDocument;
  const tag = el.tagName.toLowerCase();
  const unique = (sel: string) => {
    try {
      return doc.querySelectorAll(sel).length === 1;
    } catch {
      return false;
    }
  };
  if (el.id) {
    const sel = `#${cssEscape(el.id)}`;
    if (unique(sel)) return { selector: sel };
  }
  const name = el.getAttribute("name");
  if (name) {
    const sel = `${tag}[name="${attrEscape(name)}"]`;
    if (unique(sel)) return { selector: sel };
  }
  const tid = el.getAttribute("data-testid");
  if (tid) {
    const sel = `[data-testid="${attrEscape(tid)}"]`;
    if (unique(sel)) return { selector: sel };
  }
  const accName = accessibleName(el);
  if (accName && accName.length <= 60) {
    const role = roleOf(el);
    const same = Array.from(doc.querySelectorAll(tag)).filter((o) => roleOf(o) === role && accessibleName(o) === accName);
    if (same.length === 1 && role !== "generic") return { role, name: accName };
  }
  // positional fallback, at most four levels
  const parts: string[] = [];
  let node: Element | null = el;
  for (let depth = 0; node && depth < 4 && node.tagName !== "BODY"; depth++, node = node.parentElement) {
    const parent: Element | null = node.parentElement;
    const nodeTag = node.tagName.toLowerCase();
    if (!parent) {
      parts.unshift(nodeTag);
      break;
    }
    const sameTag = Array.from(parent.children).filter((c: Element) => c.tagName === node!.tagName);
    parts.unshift(sameTag.length > 1 ? `${nodeTag}:nth-of-type(${sameTag.indexOf(node) + 1})` : nodeTag);
  }
  return { selector: parts.join(" > ").slice(0, 300) };
}

export function installL1(deps: L1Deps): () => void {
  const { win, matcher, emit } = deps;
  const doc = win.document;
  const now = deps.now ?? (() => Date.now());
  const requireTrusted = deps.requireTrusted ?? true;
  const isTop = deps.isTop ?? (() => { try { return win.top === win; } catch { return false; } })();
  const started = now();
  const usedSlots = new Set<string>();
  const slotOf = new WeakMap<Element, string>();

  const slotFor = (el: Element): string => {
    let s = slotOf.get(el);
    if (!s) {
      s = slotName(el.getAttribute("name") || el.id || accessibleName(el) || "field", usedSlots);
      slotOf.set(el, s);
    }
    return s;
  };
  const skip = () => deps.onSkipped?.();
  const ok = (e: Event) => deps.active() && (!requireTrusted || e.isTrusted);
  const step = (partial: Omit<RecordedStep, "t_ms">) => emit({ ...partial, t_ms: Math.max(0, now() - started) });
  const safe = <E extends Event>(fn: (e: E) => void) => (e: E) => {
    try {
      fn(e);
    } catch {
      // never break the page
    }
  };

  const onClick = safe((e: MouseEvent) => {
    if (!ok(e) || !(e.target instanceof win.Element)) return;
    const el = e.target.closest("a[href], button, input, select, summary, [role=button], [role=link], [role=tab], [role=menuitem]") ?? null;
    if (!el) return;
    if (matcher.inSensitiveContext(el)) return skip();
    const tag = el.tagName.toLowerCase();
    const type = (el as HTMLInputElement).type?.toLowerCase();
    // text-like fields and selects are recorded on change, with a slot, not on click
    if (tag === "select" || (tag === "input" && !["button", "submit", "reset", "image", "checkbox", "radio"].includes(type))) return;
    step({ op: "click", ...locate(el) });
  });

  const onChange = safe((e: Event) => {
    if (!ok(e) || !(e.target instanceof win.Element)) return;
    const el = e.target;
    if (!isFormField(el)) return;
    if (matcher.inSensitiveContext(el)) return skip();
    const tag = el.tagName.toLowerCase();
    const type = ((el as HTMLInputElement).type || "").toLowerCase();
    if (type === "checkbox" || type === "radio") return; // recorded as the click that caused it
    // The value is never read: only that this field changed, and which slot stands for it.
    if (tag === "select") step({ op: "select", ...locate(el), param: slotFor(el) });
    else step({ op: "fill", ...locate(el), param: slotFor(el), input_type: type || (tag === "textarea" ? "textarea" : "text") });
  });

  const emitGoto = () => {
    if (!isTop || !deps.active()) return;
    const url = `${win.location.origin}${templatePath(win.location.pathname)}`;
    if (/^https?:\/\/[A-Za-z0-9._:/?=&%#-]+$/.test(url)) step({ op: "goto", url });
  };

  doc.addEventListener("click", onClick, { capture: true, passive: true });
  doc.addEventListener("change", onChange, { capture: true, passive: true });
  win.addEventListener("popstate", emitGoto);
  emitGoto();
  return () => {
    doc.removeEventListener("click", onClick, true);
    doc.removeEventListener("change", onChange, true);
    win.removeEventListener("popstate", emitGoto);
  };
}
