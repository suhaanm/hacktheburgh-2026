// The Home task box ("What should Knack do?"): the words, the checks and the shapes, pure. The task service is Track T's (task API contract v1: POST /agent/tasks
// with {text, source}, answered 201 {task_id, route, summary, needs_consent|null, question|null}); the calls themselves live in taskClient.ts.
// Rules this file keeps: a task is something the worker typed or said and then sent (never auto-sent, never pre-filled for them); a consent card is only ever
// answered by a real click on one of ITS buttons (the choices are a closed list, never a string the service sent); and when no service answered, nothing was
// started and the box says so, never a plan it does not have.

export const TASK_MAX = 500;
export type TaskSource = "typed" | "voice";

export const BOX_LABEL = "What should Knack do?";
export const BOX_PLACEHOLDER = "Type a task, then press Enter";
export const NOT_STARTED = "Knack's task service is not running, so nothing was started.";
export const TOO_MANY = "Three tasks are already running. Wait for one to finish, or stop one.";
export const SEND_FAILED = "That did not go through. Nothing was started.";
export const TOO_LONG = `Keep it under ${TASK_MAX} characters.`;
export const PLANNING = "Knack will plan this.";

/** Characters that never belong in a task: controls and the bidirectional overrides that can make text read backwards. Written as code points (no invisible characters in source). */
const dropped = (cp: number): boolean => cp <= 0x1f || (cp >= 0x7f && cp <= 0x9f) || cp === 0x2028 || cp === 0x2029 || (cp >= 0x202a && cp <= 0x202e) || (cp >= 0x2066 && cp <= 0x2069);

export type TaskCheck = { ok: true; text: string } | { ok: false; message: string | null };

/**
 * What was typed, checked. Line breaks and runs of spaces become single spaces, the ends are trimmed. Nothing at all is "not sendable" with no message (the box simply
 * waits). Over TASK_MAX is refused with a message, never cut: what is sent is what the worker saw.
 */
export function checkTask(raw: unknown): TaskCheck {
  if (typeof raw !== "string") return { ok: false, message: null };
  const flat = Array.from(raw).map((c) => (dropped(c.codePointAt(0) ?? 0) ? " " : c)).join("").replace(/\s+/g, " ").trim();
  if (!flat || !/[\p{L}\p{N}]/u.test(flat)) return { ok: false, message: null };
  if (Array.from(flat).length > TASK_MAX) return { ok: false, message: TOO_LONG };
  return { ok: true, text: flat };
}

/* -- What the service answers ------------------------------------------------------------------------------------------------------- */

const str = (v: unknown, max: number): string => (typeof v === "string" ? v.replace(/\s+/g, " ").trim().slice(0, max) : "");
const strs = (v: unknown, n: number, max: number): string[] => (Array.isArray(v) ? v.map((x) => str(x, max)).filter(Boolean).slice(0, n) : []);

export type ConsentChoice = "allow" | "everything" | "decline";
export interface ConsentCard {
  kind: string; scope: string; can: string[]; cannot: string[]; folder: string | null; cost: string | null; maxMinutes: number | null;
  allowLabel: string; declineLabel: string; more: { id: "everything"; label: string }[];
}
export interface QuestionCard { text: string; options: { id: string; label: string }[] }
export interface Submitted { id: string; route: string; summary: string; consent: ConsentCard | null; question: QuestionCard | null }

/** The consent card from `needs_consent`, or null when there is none or it says nothing the worker could read (then nothing is asked: a card with no scope is not a consent). */
export function parseConsent(c: unknown): ConsentCard | null {
  if (!c || typeof c !== "object") return null;
  const o = c as Record<string, unknown>;
  const scope = str(o.scope_text, 400);
  if (!scope) return null;
  const b = (o.buttons && typeof o.buttons === "object" ? o.buttons : {}) as Record<string, unknown>;
  const more = (Array.isArray(b.more) ? b.more : []).flatMap((m) => {
    const x = (m && typeof m === "object" ? m : {}) as Record<string, unknown>;
    return x.id === "everything" ? [{ id: "everything" as const, label: str(x.label, 60) || "Allow everything for this task" }] : [];
  }).slice(0, 1);
  const mm = Number(o.max_minutes);
  return {
    kind: str(o.kind, 30), scope, can: strs(o.can, 6, 120), cannot: strs(o.cannot, 6, 120), folder: str(o.folder, 200) || null, cost: str(o.cost_note, 120) || null,
    maxMinutes: Number.isInteger(mm) && mm >= 1 && mm <= 1440 ? mm : null,
    allowLabel: str(b.allow, 60) || "Allow for this task", declineLabel: str(b.decline, 60) || "Not now", more,
  };
}

export function parseQuestion(q: unknown): QuestionCard | null {
  if (!q || typeof q !== "object") return null;
  const o = q as Record<string, unknown>;
  const text = str(o.text, 300);
  const options = (Array.isArray(o.options) ? o.options : []).flatMap((x) => {
    const r = (x && typeof x === "object" ? x : {}) as Record<string, unknown>;
    const id = str(r.id, 60), label = str(r.label, 80);
    return id && label ? [{ id, label }] : [];
  }).slice(0, 6);
  return text && options.length > 0 ? { text, options } : null;
}

/** The 201 answer, made safe. Null when it carries no task id (nothing was started, whatever else it says). */
export function parseSubmitted(body: unknown): Submitted | null {
  if (!body || typeof body !== "object") return null;
  const o = (("data" in (body as object) && (body as { data?: unknown }).data && typeof (body as { data?: unknown }).data === "object") ? (body as { data: unknown }).data : body) as Record<string, unknown>;
  const id = str(o.task_id, 80);
  if (!id) return null;
  return { id, route: str(o.route, 30) || "unclear", summary: str(o.summary, 200), consent: parseConsent(o.needs_consent), question: parseQuestion(o.question) };
}

/** The one plain line shown at once: the service's own summary, else the fixed "Knack will plan this." (and for a task the service could not place, that it is not sure). */
export function summaryLine(s: Pick<Submitted, "summary" | "route">): string {
  if (s.summary) return s.summary;
  return s.route === "unclear" ? "Knack is not sure what you mean yet." : PLANNING;
}

/** What to say when the service refused or failed. 429 is the limit of three at a time; anything else is one fixed sentence (the engine's message is shown when it has one). */
export function sendError(status: number | null | undefined, code: string | null | undefined, message: string | null | undefined): string {
  if (status === 429 || code === "too_many_tasks") return TOO_MANY;
  const m = typeof message === "string" ? message.trim() : "";
  return m && m.length <= 160 && status !== 403 ? m : SEND_FAILED;
}

/** The buttons of a consent card, in the order they are drawn: Allow and Not now of equal weight, then the small More that reveals the wider choice. The ids are closed. */
export function consentButtons(c: ConsentCard): { main: { id: ConsentChoice; label: string }[]; more: { id: ConsentChoice; label: string }[] } {
  return { main: [{ id: "allow", label: c.allowLabel }, { id: "decline", label: c.declineLabel }], more: c.more };
}

/* -- Examples ----------------------------------------------------------------------------------------------------------------------- */

/** Up to three short examples that FILL the box when clicked (they never send). Role-aware; a role with none known gets the general ones. */
export function examplesFor(role: string | null | undefined): string[] {
  switch (role) {
    case "benefits-processor": return ["Check this household's entitlement", "Write up the case note"];
    case "data-analyst": return ["Profile this CSV", "Chart revenue by month"];
    case "programmer": return ["Summarise today's commits", "List the failing tests"];
    default: return ["Summarise what I did today", "Find a file for me"];
  }
}
