// L0 capture. Emits records of: nav, click, focus, scroll depth bin, copy and paste (flags only), search
// (hashed query and length only). Never reads page text, URLs, field values or the clipboard.
// Fields that match the sensitive list, or sit in a form that holds one, produce no event at all.
// Only trusted (user-originated) events are recorded, so a hostile page cannot forge activity.
import { hashDomain, hashLabel, hashQuery } from "../shared/hash";
import { accessibleName, INTERACTIVE_SELECTOR, interactiveAncestor, isFormField, roleOf } from "../shared/dom";
import type { SensitiveMatcher } from "../shared/sensitive";
import type { CaptureRecord, MetaValue, Target } from "../shared/types";
import type { Zoner } from "../shared/zones";

export interface CaptureDeps {
  win: Window & typeof globalThis;
  salt: string;
  matcher: SensitiveMatcher;
  zoner: Zoner;
  emit: (rec: CaptureRecord) => void;
  now?: () => number;
  /** Production: true. Tests that dispatch synthetic events set false; one test pins the true behaviour. */
  requireTrusted?: boolean;
  isTop?: boolean;
}

const SEARCH_NAME_RE = /^(q|query|search|s|keyword|keywords|term|terms)$/i;
const SCROLL_MIN_RANGE_PX = 50;
const SCROLL_THROTTLE_MS = 750;
const FOCUS_DEDUPE_MS = 1000;
const SEARCH_DEDUPE_MS = 1500;
const NAV_DEDUPE_MS = 400;

export function domainHashOf(win: Window, salt: string): string {
  return hashDomain(salt, win.location.host);
}

export function installCapture(deps: CaptureDeps): () => void {
  const { win, salt, matcher, zoner, emit } = deps;
  const doc = win.document;
  const now = deps.now ?? (() => Date.now());
  const requireTrusted = deps.requireTrusted ?? true;
  const isTop = deps.isTop ?? (() => { try { return win.top === win; } catch { return false; } })();
  const domain = () => domainHashOf(win, salt);

  const trusted = (e: Event) => !requireTrusted || e.isTrusted;
  const safe = <E extends Event>(fn: (e: E) => void) => (e: E) => {
    try {
      fn(e);
    } catch {
      // capture must never break the page
    }
  };

  /** Target and zone for an element, or null when the element must not be recorded. */
  const describe = (raw: Element, opts: { interactiveOnly?: boolean } = {}): { target: Target; zone?: string } | null => {
    const interactive = interactiveAncestor(raw);
    const el = interactive ?? raw;
    if (matcher.inSensitiveContext(el) || matcher.inSensitiveContext(raw)) return null;
    if (opts.interactiveOnly && !interactive) return null;
    const role = roleOf(el);
    const target: Target = { role, domain_hash: domain() };
    if (interactive) {
      const name = accessibleName(interactive);
      if (name && !matcher.isSensitiveText(name)) target.label_hash = hashLabel(salt, name);
    }
    return { target, zone: zoner.forElement(el, role) };
  };

  const withZone = (meta: Record<string, MetaValue>, zone: string | undefined) => {
    if (zone) meta.zone = zone;
    return meta;
  };

  // ---- click
  const onClick = safe((e: MouseEvent) => {
    if (!trusted(e) || !(e.target instanceof win.Element)) return;
    const d = describe(e.target);
    if (!d) return;
    emit({ type: "click", target: d.target, meta: withZone({}, d.zone) });
  });

  // ---- focus (form fields and other interactive controls)
  let lastFocus: { el: Element | null; at: number } = { el: null, at: 0 };
  const onFocus = safe((e: FocusEvent) => {
    if (!trusted(e) || !(e.target instanceof win.Element)) return;
    const el = e.target;
    if (!isFormField(el) && !el.matches(INTERACTIVE_SELECTOR)) return;
    const t = now();
    if (lastFocus.el === el && t - lastFocus.at < FOCUS_DEDUPE_MS) return;
    lastFocus = { el, at: t };
    const d = describe(el);
    if (!d) return;
    emit({ type: "focus", target: d.target, meta: withZone({}, d.zone) });
  });

  // ---- scroll depth bins (0 to 4), emitted when the bin changes, throttled
  const lastBin = new WeakMap<object, number>();
  let lastScrollAt = -Infinity;
  const onScroll = safe((e: Event) => {
    if (!trusted(e)) return;
    const t = now();
    if (t - lastScrollAt < SCROLL_THROTTLE_MS) return;
    const isDoc = e.target === doc || e.target === win;
    const scroller = isDoc ? (doc.scrollingElement ?? doc.documentElement) : (e.target instanceof win.Element ? e.target : null);
    if (!scroller) return;
    const range = scroller.scrollHeight - scroller.clientHeight;
    if (!(range >= SCROLL_MIN_RANGE_PX)) return;
    const bin = Math.min(4, Math.max(0, Math.floor((scroller.scrollTop / range) * 5)));
    if (lastBin.get(scroller) === bin) return;
    lastBin.set(scroller, bin);
    lastScrollAt = t;
    let target: Target = { domain_hash: domain() };
    let zone: string | undefined;
    if (isDoc) zone = zoner.forScroll(doc);
    else {
      const d = describe(scroller);
      if (!d) return;
      target = d.target;
      zone = d.zone;
    }
    emit({ type: "scroll", target, meta: withZone({ depth_bin: bin }, zone) });
  });

  // ---- copy and paste: flags only. The clipboard and the selection text are never read.
  // The browser may target a copy event at the focused field, the selection's container or the body, so every
  // candidate is checked: if any is sensitive nothing is emitted. Selection text is never read.
  const copyCandidates = (target: EventTarget | null): Element[] => {
    const out: Element[] = [];
    if (target instanceof win.Element) out.push(target);
    const node = win.getSelection?.()?.anchorNode ?? null;
    const anchor = node ? (node.nodeType === 1 ? (node as Element) : node.parentElement) : null;
    if (anchor) out.push(anchor);
    if (doc.activeElement) out.push(doc.activeElement);
    return out;
  };
  const onCopy = safe((e: ClipboardEvent) => {
    if (!trusted(e)) return;
    const cands = copyCandidates(e.target);
    if (!cands.length || cands.some((c) => matcher.inSensitiveContext(c))) return;
    const el = cands.find((c) => c !== doc.body && c !== doc.documentElement) ?? cands[0]!;
    const d = describe(el);
    if (!d) return;
    emit({ type: "copy", target: d.target, meta: withZone({}, d.zone) });
  });
  const onPaste = safe((e: ClipboardEvent) => {
    if (!trusted(e) || !(e.target instanceof win.Element)) return;
    const d = describe(e.target);
    if (!d) return;
    emit({ type: "paste", target: d.target, meta: withZone({}, d.zone) });
  });

  // ---- search: hashed query and length only
  const isSearchField = (el: Element): el is HTMLInputElement => {
    if (el.tagName !== "INPUT" && el.getAttribute("role") !== "searchbox") return false;
    const type = ((el as HTMLInputElement).type || "").toLowerCase();
    if (type === "search" || el.getAttribute("role") === "searchbox") return true;
    if (!["text", ""].includes(type)) return false;
    return SEARCH_NAME_RE.test(el.getAttribute("name") ?? "") || SEARCH_NAME_RE.test(el.id) ||
      /search/i.test(el.getAttribute("aria-label") ?? "") || /search/i.test(el.getAttribute("placeholder") ?? "");
  };
  let lastSearch = { q: "", at: -Infinity };
  const emitSearch = (field: HTMLInputElement) => {
    if (matcher.inSensitiveContext(field)) return;
    const raw = (field.value ?? "") as string;
    const q = raw.replace(/\s+/g, " ").trim();
    if (!q) return;
    const t = now();
    if (q === lastSearch.q && t - lastSearch.at < SEARCH_DEDUPE_MS) return;
    lastSearch = { q, at: t };
    const target: Target = { role: "searchbox", domain_hash: domain() };
    const name = accessibleName(field);
    if (name && !matcher.isSensitiveText(name)) target.label_hash = hashLabel(salt, name);
    const zone = zoner.forElement(field, "searchbox") ?? "search_box";
    emit({ type: "search", target, meta: { len: Math.min(q.length, 500), q_hash: hashQuery(salt, q), zone } });
  };
  const onKeydown = safe((e: KeyboardEvent) => {
    if (!trusted(e) || e.key !== "Enter" || !(e.target instanceof win.Element) || !isSearchField(e.target)) return;
    emitSearch(e.target);
  });
  const onSubmit = safe((e: Event) => {
    if (!trusted(e) || !(e.target instanceof win.HTMLFormElement)) return;
    const form = e.target;
    const field = Array.from(form.querySelectorAll("input, [role=searchbox]")).find(isSearchField);
    if (field) emitSearch(field);
  });

  // ---- navigation (top frame only): domain hash and zone, never a URL
  let lastNav = -Infinity;
  const emitNav = (spa: boolean) => {
    if (!isTop) return;
    const t = now();
    if (t - lastNav < NAV_DEDUPE_MS) return;
    lastNav = t;
    const meta: Record<string, MetaValue> = { spa };
    const zone = zoner.forNav(doc);
    if (zone) meta.zone = zone;
    const markers = zoner.markersFor(zone, doc);
    emit({ type: "nav", target: { role: "document", domain_hash: domain() }, meta, ...(markers ? { markers } : {}) });
  };
  const onSpa = safe(() => emitNav(true));

  const opts = { capture: true, passive: true } as const;
  doc.addEventListener("click", onClick, opts);
  doc.addEventListener("focusin", onFocus, opts);
  doc.addEventListener("scroll", onScroll, opts);
  win.addEventListener("scroll", onScroll, opts);
  doc.addEventListener("copy", onCopy, opts);
  doc.addEventListener("paste", onPaste, opts);
  doc.addEventListener("keydown", onKeydown, opts);
  doc.addEventListener("submit", onSubmit, opts);
  win.addEventListener("popstate", onSpa);
  win.addEventListener("hashchange", onSpa);
  const nav = (win as unknown as { navigation?: EventTarget }).navigation;
  nav?.addEventListener("navigatesuccess", onSpa);

  emitNav(false);

  return () => {
    doc.removeEventListener("click", onClick, true);
    doc.removeEventListener("focusin", onFocus, true);
    doc.removeEventListener("scroll", onScroll, true);
    win.removeEventListener("scroll", onScroll, true);
    doc.removeEventListener("copy", onCopy, true);
    doc.removeEventListener("paste", onPaste, true);
    doc.removeEventListener("keydown", onKeydown, true);
    doc.removeEventListener("submit", onSubmit, true);
    win.removeEventListener("popstate", onSpa);
    win.removeEventListener("hashchange", onSpa);
    nav?.removeEventListener("navigatesuccess", onSpa);
  };
}
