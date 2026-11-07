// Command palette logic, pure: the items, the fuzzy match, the rows (capped at seven), and the keyboard index maths.
// No React, no network, no router here, so it is tested without a browser. The view (Palette.tsx) only draws what this returns.
import type { AdminInsight, WirePointer } from "../firm/wire";
import { FIRM_TABS, entriesFor, type NavGroup } from "./navModel";
import type { ViewRole } from "./viewAs";

export type ItemKind = "screen" | "firm_tab" | "pointer" | "insight" | "action";
export type ActionId = "tour" | "view_admin" | "view_worker" | "stop" | "monday" | "about" | "settings" | "ask" | "pause" | "accessibility";
export type PaletteTarget = { type: "route"; path: string } | { type: "action"; action: ActionId; phrase?: string };

/** The desktop-only commands that exist right now (the page offers a command only when the desktop app can do it: no dead rows). */
export interface PaletteCaps { ask: boolean; pause: boolean; accessibility: boolean }
export const NO_CAPS: PaletteCaps = { ask: false, pause: false, accessibility: false };

export interface PaletteItem {
  id: string;
  kind: ItemKind;
  label: string;
  hint: string;
  /** Extra words the match also reads (at a lower weight). */
  also: string;
  /** The heading it sits under. */
  group: string;
  target: PaletteTarget;
}

export const KIND_LABEL: Record<ItemKind, string> = { screen: "Screen", firm_tab: "Firm view", pointer: "Pointer", insight: "Insight", action: "Action" };
export const GROUP_LABEL: Record<NavGroup, string> = { primary: "Go to", admin: "Admin", understand: "Understand your work", behind: "Behind the scenes", reviewers: "For reviewers", hidden: "" };
export const GROUP_POINTERS = "This week";
export const GROUP_INSIGHTS = "Firm insights";
export const GROUP_FIRM = "Firm";
export const GROUP_ACTIONS = "Do";
export const GROUP_ASK = "Ask";

/** The most rows any default list shows. "Show all" reveals the rest. */
export const DEFAULT_CAP = 7;

/** Where a worker pointer leads: its one action, or back to Your week when it has none. */
export function pointerPath(p: Pick<WirePointer, "action">): string {
  return p.action ? `/${p.action.to}${p.action.query ? `?${p.action.query}` : ""}` : "/home";
}

/** Where an admin insight leads: the Firm overview, with that insight opened. */
export const insightPath = (id: string): string => `/firm?insight=${encodeURIComponent(id)}`;

export interface ExtraItems { pointers?: WirePointer[]; insights?: AdminInsight[] }

/**
 * Everything the palette can go to, in the order it is listed: screens, the Firm views, the insights, then the actions.
 * Role-aware: the Worker view never gets an admin screen, a Firm view, an admin insight or the brief.
 */
export function buildItems(view: ViewRole, extra: ExtraItems = {}, caps: PaletteCaps = NO_CAPS): PaletteItem[] {
  const items: PaletteItem[] = [];
  for (const e of entriesFor(view)) {
    items.push({ id: `screen:${e.id}`, kind: "screen", label: e.label, hint: e.hint, also: e.also ?? "", group: GROUP_LABEL[e.group], target: { type: "route", path: `/${e.id}` } });
  }
  if (view === "admin") {
    // "Overview" is the Firm screen itself and "Firm brief" has its own action, so neither is listed twice.
    for (const t of FIRM_TABS) {
      if (t.id === "overview" || t.id === "brief") continue;
      items.push({ id: `tab:${t.id}`, kind: "firm_tab", label: `Firm: ${t.label}`, hint: t.hint, also: "admin", group: GROUP_FIRM, target: { type: "route", path: t.path } });
    }
    for (const i of extra.insights ?? []) {
      items.push({ id: `insight:${i.id}`, kind: "insight", label: i.headline, hint: i.polarity_label ?? "Firm insight", also: `${i.kind ?? ""} ${i.role === "all" ? "" : i.role}`.trim(), group: GROUP_INSIGHTS, target: { type: "route", path: insightPath(i.id) } });
    }
  } else {
    for (const p of extra.pointers ?? []) {
      items.push({ id: `pointer:${p.id}`, kind: "pointer", label: p.headline, hint: p.polarity_label ?? p.action?.label ?? "Pointer", also: p.kind, group: GROUP_POINTERS, target: { type: "route", path: pointerPath(p) } });
    }
  }
  const act = (id: string, label: string, hint: string, also: string, action: ActionId, group = GROUP_ACTIONS): PaletteItem => ({ id: `action:${id}`, kind: "action", label, hint, also, group, target: { type: "action", action } });
  items.push(act("settings", "Settings", "Live models, interruptions, coaching, appearance", "preferences options live models notices", "settings", "Go to"));
  items.push(act("stop", "Stop everything", "Stops every agent and routine now", "kill halt emergency", "stop"));
  if (caps.pause) items.push(act("pause", "Pause for 1 hour", "Nothing starts for an hour", "snooze quiet break", "pause"));
  if (view === "worker") items.push(act("monday", "Copy my Monday note", "Your week as a short note you can paste", "share summary pointers", "monday"));
  items.push(act("about", "Explain this screen", "What it is and where the numbers come from", "about help what is this", "about"));
  items.push({ id: "action:delete", kind: "action", label: "Delete my data", hint: "Opens Your data, where each part has a Forget", also: "forget erase remove privacy memory", group: GROUP_ACTIONS, target: { type: "route", path: "/your-data" } });
  items.push(act("tour", "Take the tour", "A short walk through the main screens", "help guide walkthrough", "tour"));
  if (caps.accessibility) items.push(act("accessibility", "Open System Settings for Accessibility", "Where you allow Knack to point at the screen", "permission macos screen recording", "accessibility"));
  if (caps.ask) items.push(act("ask", "Ask Knack", "Tap to type, hold Option-Space to talk", "chat voice question", "ask", GROUP_ASK));
  if (view === "worker") {
    items.push({ id: "action:view_admin", kind: "action", label: "Switch to the Admin view", hint: "Shows the Firm screen. A view switch, not a permission", also: "role admin firm", group: GROUP_ACTIONS, target: { type: "action", action: "view_admin" } });
  } else {
    items.push({ id: "action:brief", kind: "action", label: "Print the firm brief", hint: "A one-page summary for the firm", also: "export pdf one-pager", group: GROUP_ACTIONS, target: { type: "route", path: "/firm/brief" } });
    items.push({ id: "action:view_worker", kind: "action", label: "Switch to Worker view", hint: "Leaves the Firm screens", also: "role worker", group: GROUP_ACTIONS, target: { type: "action", action: "view_worker" } });
  }
  return items;
}

/** The last row when what was typed matches nothing and the desktop app can take a question: it opens the Ask bar with the phrase filled in. */
export function askItem(phrase: string): PaletteItem {
  const p = phrase.trim();
  return { id: "ask:phrase", kind: "action", label: `Ask Knack: ${p}`, hint: "Opens the Ask bar with this question", also: "", group: GROUP_ASK, target: { type: "action", action: "ask", phrase: p } };
}

/* -- Fuzzy matching ----------------------------------------------------------------------------------------------------------- */

export interface TokenMatch { score: number; positions: number[] }

const range = (from: number, n: number): number[] => Array.from({ length: n }, (_, k) => from + k);
const isWordStart = (t: string, i: number): boolean => i === 0 || !/[a-z0-9]/.test(t[i - 1]);

/** The best subsequence match of `q` in `t`: every letter in order, preferring word starts and runs, with small penalties for gaps. */
function subsequence(q: string, t: string): TokenMatch | null {
  if (q.length < 2) return null; // one letter is only ever a prefix or a substring
  const maxSpan = Math.max(q.length * 3, q.length + 4); // letters scattered across a long text are a coincidence, not a match
  let best: TokenMatch | null = null;
  for (let s = t.indexOf(q[0]); s >= 0; s = t.indexOf(q[0], s + 1)) {
    const positions = [s];
    let pos = s;
    let ok = true;
    for (let k = 1; k < q.length; k++) {
      const nxt = t.indexOf(q[k], pos + 1);
      if (nxt < 0) { ok = false; break; }
      positions.push(nxt);
      pos = nxt;
    }
    if (!ok || pos - s + 1 > maxSpan) continue;
    let score = 100 + (isWordStart(t, positions[0]) ? 10 : 0);
    for (let k = 1; k < positions.length; k++) {
      const gap = positions[k] - positions[k - 1] - 1;
      if (gap === 0) score += 8;
      else score -= Math.min(gap, 20) * 0.5;
      if (isWordStart(t, positions[k])) score += 6;
    }
    score -= Math.min(positions[0], 50) * 0.2;
    if (!best || score > best.score) best = { score, positions };
  }
  return best;
}

/**
 * How well one typed word matches a piece of text, or null. Tiers, best first: the whole text, a prefix, the start of a word,
 * a plain substring, then (only when `loose`) letters in order. Case-insensitive. The positions say which letters matched, for highlighting.
 */
export function matchToken(token: string, text: string, loose = true): TokenMatch | null {
  const q = token.toLowerCase();
  const t = text.toLowerCase();
  if (!q || !t) return null;
  if (t === q) return { score: 1000, positions: range(0, q.length) };
  if (t.startsWith(q)) return { score: 800 - Math.min(t.length - q.length, 100) * 0.5, positions: range(0, q.length) };
  for (let i = t.indexOf(q); i >= 0; i = t.indexOf(q, i + 1)) {
    if (isWordStart(t, i)) return { score: 600 - Math.min(i, 100) * 0.5, positions: range(i, q.length) };
  }
  const at = t.indexOf(q);
  if (at >= 0) return { score: 400 - Math.min(at, 100) * 0.5, positions: range(at, q.length) };
  return loose ? subsequence(q, t) : null;
}

const HINT_WEIGHT = 0.4;
const ALSO_WEIGHT = 0.4;

export const tokensOf = (query: string): string[] => query.trim().toLowerCase().split(/\s+/).filter(Boolean);

export interface Scored { item: PaletteItem; score: number; positions: number[] }

/** Every typed word must match the label, the hint or the extra words; the label counts most. Null when any word matches nothing. */
export function scoreItem(tokens: string[], item: PaletteItem): Scored | null {
  if (!tokens.length) return null;
  let total = 0;
  const hit = new Set<number>();
  for (const tok of tokens) {
    const onLabel = matchToken(tok, item.label);
    // Letters-in-order is for names only. A hint or a keyword must contain the word itself.
    const onHint = matchToken(tok, item.hint, false);
    const onAlso = item.also ? matchToken(tok, item.also, false) : null;
    const best = Math.max(onLabel?.score ?? -1, (onHint?.score ?? -1) * HINT_WEIGHT, (onAlso?.score ?? -1) * ALSO_WEIGHT);
    if (best < 0) return null;
    total += best;
    onLabel?.positions.forEach((p) => hit.add(p));
  }
  return { item, score: total, positions: [...hit].sort((a, b) => a - b) };
}

/** A match much weaker than the best one is noise ("gro" is a screen name, not a word buried in someone's hint): it is dropped. */
export const KEEP_RATIO = 0.25;
export const MIN_SCORE = 40;

/**
 * Matching items, best first. Ties keep the order the items were listed in, so the result never shuffles between keystrokes.
 * Anything scoring under a quarter of the best match is left out, so a clear hit is not followed by a tail of coincidences.
 */
export function searchItems(items: PaletteItem[], query: string): Scored[] {
  const tokens = tokensOf(query);
  if (!tokens.length) return [];
  const out: { s: Scored; order: number }[] = [];
  items.forEach((item, order) => { const s = scoreItem(tokens, item); if (s) out.push({ s, order }); });
  out.sort((a, b) => b.s.score - a.s.score || a.order - b.order);
  const floor = Math.max(MIN_SCORE, (out[0]?.s.score ?? 0) * KEEP_RATIO);
  return out.filter((o) => o.s.score >= floor).map((o) => o.s);
}

/* -- Rows ---------------------------------------------------------------------------------------------------------------------- */

export type Row =
  | { type: "item"; item: PaletteItem; positions: number[] }
  | { type: "more"; count: number };

export interface RowsResult {
  rows: Row[];
  /** How many items match (all of them for an empty query). */
  total: number;
  /** Whether a "Show all" row is present. */
  capped: boolean;
}

/**
 * The rows to draw. An empty query lists the screens in menu order, at most `cap` of them, then a "Show all" row; once expanded it lists
 * every item (screens, Firm views, insights, actions). A query lists the best matches, also at most `cap`, with the same "Show all" row.
 */
export function rowsFor(items: PaletteItem[], query: string, expanded: boolean, cap = DEFAULT_CAP): RowsResult {
  const q = query.trim();
  let pool: { item: PaletteItem; positions: number[] }[];
  let total: number;
  if (!q) {
    total = items.length;
    pool = (expanded ? items : items.filter((i) => i.kind === "screen").slice(0, cap)).map((item) => ({ item, positions: [] }));
  } else {
    const hits = searchItems(items, q);
    total = hits.length;
    pool = (expanded ? hits : hits.slice(0, cap)).map((h) => ({ item: h.item, positions: h.positions }));
  }
  const rows: Row[] = pool.map((p) => ({ type: "item", item: p.item, positions: p.positions }));
  const capped = !expanded && total > pool.length;
  if (capped) rows.push({ type: "more", count: total });
  return { rows, total, capped };
}

export interface RowGroup { heading: string | null; rows: { row: Row; index: number }[] }

/** Consecutive rows under the same heading, each with its option index (the number the keyboard moves). The "Show all" row has no heading. */
export function groupRows(rows: Row[], showHeadings = true): RowGroup[] {
  const groups: RowGroup[] = [];
  rows.forEach((row, index) => {
    const heading = row.type === "item" && showHeadings ? row.item.group : null;
    const last = groups[groups.length - 1];
    if (last && last.heading === heading && row.type === "item") last.rows.push({ row, index });
    else groups.push({ heading, rows: [{ row, index }] });
  });
  return groups;
}

/* -- Keyboard ------------------------------------------------------------------------------------------------------------------ */

/** Step `delta` options from `i` among `n`, wrapping at both ends. -1 when there is nothing to move to. */
export const wrapIndex = (i: number, delta: number, n: number): number => (n <= 0 ? -1 : (((i + delta) % n) + n) % n);

export type NavKey = "ArrowDown" | "ArrowUp" | "Home" | "End" | "PageDown" | "PageUp";
export const NAV_KEYS: NavKey[] = ["ArrowDown", "ArrowUp", "Home", "End", "PageDown", "PageUp"];
export const isNavKey = (k: string): k is NavKey => (NAV_KEYS as string[]).includes(k);

/** The next active option for a navigation key. Arrows wrap; Home and End go to the ends; a page is five options and stops at the ends. */
export function moveIndex(i: number, key: NavKey, n: number): number {
  if (n <= 0) return -1;
  switch (key) {
    case "ArrowDown": return wrapIndex(i, 1, n);
    case "ArrowUp": return wrapIndex(i < 0 ? 0 : i, -1, n);
    case "Home": return 0;
    case "End": return n - 1;
    case "PageDown": return Math.min(n - 1, Math.max(0, i) + 5);
    case "PageUp": return Math.max(0, i - 5);
  }
}

/* -- Display ------------------------------------------------------------------------------------------------------------------- */

/** The label split into plain and matched runs, so the match can be shown bold and underlined (not by colour alone). */
export function segments(text: string, positions: number[]): { text: string; hit: boolean }[] {
  if (!positions.length) return [{ text, hit: false }];
  const hit = new Set(positions);
  const out: { text: string; hit: boolean }[] = [];
  let cur = "";
  let curHit = false;
  for (let i = 0; i < text.length; i++) {
    const h = hit.has(i);
    if (i > 0 && h !== curHit) { out.push({ text: cur, hit: curHit }); cur = ""; }
    cur += text[i];
    curHit = h;
  }
  if (cur) out.push({ text: cur, hit: curHit });
  return out;
}

/** The sentence read out to a screen reader after each change. */
export function resultsText(total: number): string {
  if (total <= 0) return "No results";
  return total === 1 ? "1 result" : `${total} results`;
}

/** The line shown when nothing matches: what happened and what to try. */
export const NO_RESULTS_HELP = "Try a screen name such as Growth, or a word such as stuck, calendar or privacy.";
