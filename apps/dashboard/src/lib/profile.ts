// The worker's profile as the Account menu shows it: a name and a role. Pure helpers plus one tiny store, so the rules are tests.
// The NAME is the engine's when it answers (POST /profile writes one line of the memory file, which the worker can read and delete under What Knack remembers)
// and the device's own otherwise (localStorage, this Mac only). Nothing else receives it, and an approval never carries it (auth.ts sends a method and a hash).
// The ROLE is the engine's. Changing it posts to /profile, which keeps the person, the name, the quiet hours and the capture choice, and starts the new
// role's skills clean.
import { useSyncExternalStore } from "react";

export const NAME_KEY = "understudy-display-name";
export const NAME_MAX = 60;
export const NAME_PLACEHOLDER = "Your name";
/** The link in the Account menu that opens the name editor when there is no name yet. */
export const ADD_NAME = "Add your name";
export const NAME_RULE = "Letters, spaces, hyphens and apostrophes, starting with a letter. Up to 60 characters.";

/** What GET /profile answers (the engine's own shape; extra fields are ignored). `roles` is the closed list for the role picker. */
export interface ProfileRole { id: string; name: string; summary?: string; depth?: string }
export interface Profile {
  person: string;
  role: string;
  name?: string | null;
  since?: string;
  history?: { role: string; since: string; until: string | null }[];
  roles: ProfileRole[];
}
/** The body of POST /profile: at least one of role and name. name "" or null clears it; absent keeps it. */
export interface ProfileChange { role?: string; name?: string | null }
export interface ProfileResult { person: string; role: string; name?: string | null; role_changed: boolean; previous_role: string | null }

/**
 * Characters that are never part of a name: controls, the line and paragraph separators, and the bidirectional overrides and isolates that can make text read
 * backwards. Right-to-left names stay (their letters are ordinary letters). Written as code points so the source holds no invisible character.
 */
function isDropped(cp: number): boolean {
  return cp <= 0x1f || (cp >= 0x7f && cp <= 0x9f) || cp === 0x2028 || cp === 0x2029 || (cp >= 0x202a && cp <= 0x202e) || (cp >= 0x2066 && cp <= 0x2069);
}
const spaced = (s: string): string => Array.from(s).map((ch) => (isDropped(ch.codePointAt(0) ?? 0) ? " " : ch)).join("");

/** Letters in any script (and the marks that belong to them), spaces, hyphen, apostrophes and full stops; the first character a letter. The engine checks the same rule. */
const NAME_OK = /^\p{L}[\p{L}\p{M} .'’-]*$/u;

export type NameCheck = { ok: true; name: string | null } | { ok: false; message: string };

/**
 * A typed name, checked. Spaces are collapsed and the ends trimmed first. Nothing at all is fine and means "no name" (it clears it). Anything else must follow
 * NAME_RULE: a number, an emoji or a symbol is refused with the rule, never silently cut, so what is stored is what the worker saw.
 */
export function checkName(raw: unknown): NameCheck {
  if (raw === null || raw === undefined) return { ok: true, name: null };
  if (typeof raw !== "string") return { ok: false, message: NAME_RULE };
  const flat = spaced(raw).replace(/\s+/g, " ").trim();
  if (!flat) return { ok: true, name: null };
  if (Array.from(flat).length > NAME_MAX || !NAME_OK.test(flat)) return { ok: false, message: NAME_RULE };
  return { ok: true, name: flat };
}

/** A stored or received name, or null when it is empty or breaks the rule (a stale or hand-edited value never reaches the screen). */
export function cleanName(raw: unknown): string | null {
  const c = checkName(raw);
  return c.ok ? c.name : null;
}

/** One letter for the avatar: the first letter of the name, upper-cased. Null when there is none (the avatar then shows its icon). */
export function initialOf(name: string | null): string | null {
  const first = Array.from(name ?? "").find((c) => /\p{L}/u.test(c));
  return first ? first.toLocaleUpperCase() : null;
}

/** A role id ("benefits-processor") as words, when no pack name is known: "Benefits processor". */
export function roleWords(id: string | null | undefined): string | null {
  if (!id || typeof id !== "string") return null;
  const w = id.replace(/[-_]+/g, " ").trim();
  return w ? w.charAt(0).toUpperCase() + w.slice(1) : null;
}

export interface PackLike { id: string; name: string }
/** The role as a person reads it: the pack's name when the roles are known, else the id as words, else null. */
export function roleLabel(id: string | null | undefined, packs: PackLike[] | null | undefined): string | null {
  if (!id) return null;
  return packs?.find((p) => p.id === id)?.name ?? roleWords(id);
}

/** How far a role's pack is built, in the worker's words: deep is validated, standard is a full pack, anything else a starter. Never a number. */
export const depthLabel = (depth: unknown): string => (depth === "deep" ? "Fully built and validated" : depth === "standard" ? "Full pack" : "Starter");

/** Earlier work as another role is offered when the engine reports work under a role that is not the current one. Pure so the rule is a test. */
export function earlierRoles(scope: { role?: string; roles?: { role: string; n: number }[] } | null | undefined): string[] {
  return (scope?.roles ?? []).filter((r) => r.role !== scope?.role && r.n > 0).map((r) => r.role);
}

/* -- The name store ---------------------------------------------------------------------------------------------------------------- */

function read(): string | null {
  try { return cleanName(window.localStorage.getItem(NAME_KEY)); } catch { return null; }
}

let name: string | null = typeof window === "undefined" ? null : read();
const listeners = new Set<() => void>();

export const getDisplayName = (): string | null => name;

/** Keeps a name (or forgets it for null or nothing). Returns what was kept; a name that breaks the rule is not kept. */
export function setDisplayName(raw: unknown): string | null {
  const next = cleanName(raw);
  if (next === name) return name;
  name = next;
  try { if (next) window.localStorage.setItem(NAME_KEY, next); else window.localStorage.removeItem(NAME_KEY); } catch { /* storage can be blocked: the name lasts until the page closes */ }
  listeners.forEach((l) => l());
  return name;
}

/** The engine answered who the worker is: its word about the name wins, including "none" (the worker deleted the line). Not called when the engine is down. */
export function adoptEngineName(raw: unknown): void { setDisplayName(raw); }

export function resetDisplayName(): void { name = null; listeners.forEach((l) => l()); }

export function useDisplayName(): [string | null, (v: unknown) => string | null] {
  const v = useSyncExternalStore((cb) => { listeners.add(cb); return () => listeners.delete(cb); }, () => name, () => null);
  return [v, setDisplayName];
}

/* -- What the form says ------------------------------------------------------------------------------------------------------------ */

export const SAVED_LIVE = "Saved.";
export const SAVED_EXAMPLE = "Saved on this device.";
export const SAVE_FAILED = "That did not go through. Nothing was changed.";
export const ROLE_NOTE = "Your history stays. Home, Growth and coaching follow the new role.";

/** The body to send, or null when nothing changed (the form then just closes). */
export function profileChange(was: { role: string | null; name: string | null }, now: { role: string | null; name: string | null }): ProfileChange | null {
  const out: ProfileChange = {};
  if (now.role && now.role !== was.role) out.role = now.role;
  if ((now.name ?? null) !== (was.name ?? null)) out.name = now.name ?? "";
  return out.role !== undefined || out.name !== undefined ? out : null;
}
