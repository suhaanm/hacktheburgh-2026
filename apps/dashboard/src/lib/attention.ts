import type { AttentionBadges, AttentionDigest, AttentionLearned, AttentionSettings, AttentionType, AttentionWhy } from "../types";

/** The four modes a kind of notice can be set to, loudest first. */
export const MODES = ["loud", "normal", "quiet", "digest"] as const;
export type Mode = (typeof MODES)[number];
export const MODE_LABEL: Record<Mode, string> = { loud: "Loud", normal: "Normal", quiet: "Quiet", digest: "Digest only" };
export const isMode = (m: string): m is Mode => (MODES as readonly string[]).includes(m);

/** The groups the page shows. The engine's five classes fold into four plain ones. */
export const GROUPS: { id: string; title: string; blurb: string; classes: string[] }[] = [
  { id: "needs", title: "Needs you", blurb: "Things that stop, or wait on a decision from you.", classes: ["safety", "time"] },
  { id: "now", title: "Helps in the moment", blurb: "Hints and questions while you work.", classes: ["now"] },
  { id: "wait", title: "Can wait", blurb: "Things that can be folded into one summary.", classes: ["wait"] },
  { id: "info", title: "Information", blurb: "Notes that need nothing from you.", classes: ["info"] },
];

/** A kind of notice in plain words. */
export const TYPE_LABEL: Record<string, string> = {
  kill_engaged: "Everything was stopped", injection_pause: "A page gave the agent instructions, so it paused", irreversible_decision: "A step that cannot be undone needs your click",
  run_blocked_target: "A run cannot find what it needs", run_blocked_error: "A run hit an error", approval_blocking: "An approval is holding up a job", calendar_deadline: "A calendar deadline is close",
  cue_cue: "A hint while you work", cue_ask: "A question when you seem stuck", cue_offer: "An offer of a hand after a long stall", voice_line: "A spoken line",
  kill_cleared: "Stop was cleared", help_level_changed: "Your help level changed", routine_proposal: "A routine it could run for you", briefing_ready: "Your briefing is ready",
  approval_waiting: "An approval is waiting", run_finished: "A background run finished", morning_report: "The morning report", service_degraded: "A service is slow or down", attention_digest: "A summary is ready",
};
export const typeLabel = (t: string): string => TYPE_LABEL[t] ?? (t.charAt(0).toUpperCase() + t.slice(1).replace(/_/g, " "));

/** What each mode does for each class, from the attention design. Safety ignores every mode. */
export const MODE_LINE: Record<string, Record<Mode, string>> = {
  time: {
    loud: "Shown at once, with one reminder after about 10 minutes.",
    normal: "Shown at once, with one reminder after about 20 minutes.",
    quiet: "Counted in the menu bar. Shown once at your next pause, only for approvals and deadlines. No reminder.",
    digest: "Counted in the menu bar and listed in your summary. Nothing pops up.",
  },
  now: {
    loud: "Hints and questions while you work, a few more than usual.",
    normal: "Hints and questions while you work, when the coach decides they are worth it.",
    quiet: "No offers, and no questions unless you ask. About half as many hints.",
    digest: "Silent unless you ask.",
  },
  wait: {
    loud: "One roll-up notice at your next pause.",
    normal: "A summary, or one roll-up notice at a pause if something needs you.",
    quiet: "A summary and a note on the dashboard only.",
    digest: "A summary only.",
  },
  info: {
    loud: "The same as Normal.",
    normal: "Logged. The help level may show for two seconds.",
    quiet: "Logged only.",
    digest: "Logged only.",
  },
};
export const SAFETY_LINE = "Always shown once, and it stays visible until it is resolved. No setting changes that.";
export const modeLine = (cls: string, mode: string): string => (cls === "safety" ? SAFETY_LINE : isMode(mode) ? MODE_LINE[cls]?.[mode] ?? "" : "");

export interface NoticeRow { type: string; label: string; cls: string; mode: string; fixed: boolean }
export interface NoticeGroup { id: string; title: string; blurb: string; rows: NoticeRow[] }

/** The kinds of notice grouped for display, in the engine's order; empty groups are left out. */
export function groupTypes(types: AttentionType[]): NoticeGroup[] {
  return GROUPS.map((g) => ({
    id: g.id, title: g.title, blurb: g.blurb,
    rows: types.filter((t) => g.classes.includes(t.class)).map((t) => ({ type: t.type, label: typeLabel(t.type), cls: t.class, mode: t.mode, fixed: t.fixed })),
  })).filter((g) => g.rows.length > 0);
}

/** The settings as the screen holds them after one change. A fixed (safety) row is never changed here; the engine would refuse it too. */
export function withMode(s: AttentionSettings, type: string, mode: Mode): AttentionSettings {
  const row = s.types.find((t) => t.type === type);
  if (!row || row.fixed) return s;
  const modes = { ...s.modes };
  if (mode === "normal") delete modes[type]; else modes[type] = mode;
  return { ...s, modes, types: s.types.map((t) => (t.type === type ? { ...t, mode } : t)) };
}

export const BUDGET_MIN = 0, BUDGET_MAX = 40, BUDGET_DEFAULT = 10;
export const clampBudget = (n: number): number => Math.max(BUDGET_MIN, Math.min(BUDGET_MAX, Math.round(Number.isFinite(n) ? n : BUDGET_DEFAULT)));
export function budgetWords(b: number): string {
  if (b <= 0) return "No notices pop up: everything that can wait goes into the summary.";
  return `Up to ${b} ${b === 1 ? "notice" : "notices"} a day that interrupt you. The rest wait for the summary.`;
}
export const BUDGET_FLOOR = "Safety stops and approvals that block a job always stay visible, whatever this says.";

/* -- Today -------------------------------------------------------------------------------------------------------------------- */

export type TodayState = "shown" | "held" | "dropped" | "passive" | "other";
export interface TodayLine { state: TodayState; code: string; n: number; /** The engine's own fixed sentence, or null when it sent only a count. */ text: string | null }
export interface TodaySummary { shown: number; held: number; dropped: number; passive: number; lines: TodayLine[] }

const STATES = new Set<string>(["shown", "held", "dropped", "passive"]);
const RANK: Record<TodayState, number> = { shown: 0, passive: 1, held: 2, dropped: 3, other: 4 };

/**
 * Today's counts. The engine sends `today_detail` rows with their own fixed reason sentence; that wording is shown as sent (the page
 * keeps no copy of it). An older engine sends only `today` counters keyed like "held:held_typing": those become counts with no reason.
 */
export function todaySummary(today: Record<string, number> | undefined, detail?: AttentionDigest["today_detail"]): TodaySummary {
  const out: TodaySummary = { shown: 0, held: 0, dropped: 0, passive: 0, lines: [] };
  const add = (head: string, code: string, n: number, text: string | null) => {
    if (typeof n !== "number" || !Number.isFinite(n) || n <= 0) return;
    const state: TodayState = STATES.has(head) ? (head as TodayState) : "other";
    if (state !== "other") out[state] += n;
    out.lines.push({ state, code, n, text: text && text.trim() ? text : null });
  };
  if (Array.isArray(detail) && detail.length > 0) for (const d of detail) add(String(d.state), String(d.code ?? ""), d.n, typeof d.reason_text === "string" ? d.reason_text : null);
  else for (const [key, n] of Object.entries(today ?? {})) { const [head, ...rest] = key.split(":"); add(head, rest.join(":"), n, null); }
  out.lines.sort((a, b) => RANK[a.state] - RANK[b.state] || b.n - a.n);
  return out;
}

export function todayHeadline(t: TodaySummary, b: { used: number; per_day: number }): string {
  const parts = [`${t.shown} shown`, `${t.held} held`, `${t.dropped} dropped`];
  if (t.passive > 0) parts.push(`${t.passive} left as quiet notes`);
  return `Today: ${parts.join(", ")}. ${b.used} of ${b.per_day} interrupting notices used.`;
}

export const STATE_WORD: Record<TodayState, string> = { shown: "shown", passive: "quiet", held: "held", dropped: "dropped", other: "" };

/** One needs-you entry from the digest, in words: "An approval is holding up a job (2)". */
export function needsYouLine(i: { type: string; count: number }): string {
  return `${typeLabel(i.type)}${i.count > 1 ? ` (${i.count})` : ""}`;
}

/** The reason for one item, in the engine's own words, and the steps that led to it. A step with no recorded reason is left out. */
export function whyLines(w: AttentionWhy | null | undefined): { reason: string; steps: { state: string; text: string }[] } {
  if (!w) return { reason: "", steps: [] };
  const steps = (w.transitions ?? []).filter((t) => typeof t.reason_text === "string" && t.reason_text && t.reason_text !== "No reason was recorded.").map((t) => ({ state: t.state, text: t.reason_text }));
  return { reason: w.reason_text ?? "", steps };
}

/* -- Learned quieting and the banner ----------------------------------------------------------------------------------------- */

const hourText = (h: number): string => `${String(h).padStart(2, "0")}:00`;

/** What the layer learned from how you reacted, one plain sentence each. It can only make a kind of notice quieter. */
export function learnedLines(learned: Record<string, AttentionLearned> | undefined): { type: string; text: string }[] {
  return Object.entries(learned ?? {}).map(([type, l]) => {
    const n = typeof l?.n === "number" && Number.isFinite(l.n) && l.n >= 0 ? Math.floor(l.n) : null;
    const hours = Array.isArray(l?.drop_hours) ? (l.drop_hours as number[]).filter((h) => typeof h === "number" && Number.isInteger(h) && h >= 0 && h <= 23).sort((a, b) => a - b) : [];
    const never = Array.isArray(l?.never_subjects) ? l.never_subjects.length : typeof l?.never_subjects === "number" ? l.never_subjects : 0;
    const bits = [
      n != null ? `from ${n} ${n === 1 ? "reaction" : "reactions"}` : null,
      hours.length ? `especially around ${hours.map(hourText).join(", ")}` : null,
      never > 0 ? `${never} ${never === 1 ? "thing you chose never for" : "things you chose never for"}` : null,
    ].filter(Boolean);
    return { type, text: `“${typeLabel(type)}” is quieter than usual${bits.length ? `: ${bits.join("; ")}` : ""}.` };
  });
}

export interface BannerReading { show: boolean; text: string; summary: boolean }
/** The passive banner: counts only. The stopped state belongs to the Stop pill, so it never shows here. */
export function bannerReading(badges: AttentionBadges | null | undefined, digestReady: boolean): BannerReading {
  if (!badges) return { show: false, text: "", summary: false };
  const needs = badges.needs_you ?? 0, waiting = badges.waiting ?? 0;
  const parts: string[] = [];
  if (needs > 0) parts.push(`${needs} ${needs === 1 ? "needs" : "need"} you`);
  const other = Math.max(0, waiting - needs);
  if (other > 0) parts.push(`${other} ${other === 1 ? "is" : "are"} waiting`);
  const show = parts.length > 0 || digestReady;
  return { show, text: parts.join(", "), summary: digestReady };
}

export const hasLines = (d: Pick<AttentionDigest, "lines"> | null | undefined): boolean => !!d && d.lines.length > 0;
