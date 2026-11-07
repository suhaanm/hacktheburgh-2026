// The copy lint of KNACK_UX section 5 (banned patterns) and rule 6 (rename): pure functions that say what in a piece of visible text is not allowed.
// Used by copy-lint.test.ts over source strings, fixtures and the text the models build. The rendered side is scripts/check-copy.mjs, which reads the
// same file of phrases (docs/knack-ux/banned-phrases.json) in a real page. Nothing here reads a file or touches the DOM.

export interface BannedConfig {
  phrases: string[];
  visible_words: string[];
  visible_old_name: { word: string; allow: string[] };
  jargon_in_default_view: string[];
}

export type Finding = { kind: "phrase" | "word" | "old name" | "name"; match: string };

const escape = (s: string): string => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** A phrase as a whole-word, case-insensitive pattern. A boundary is only asked for where the phrase begins or ends with a word character ("note:" has none at the end). */
export function phraseRegex(phrase: string): RegExp {
  const head = /^\w/.test(phrase) ? "\\b" : "";
  const tail = /\w$/.test(phrase) ? "\\b" : "";
  return new RegExp(`${head}${escape(phrase)}${tail}`, "i");
}

/**
 * Internal identifiers that carry the old name and are not copy: storage keys (understudy-theme), events (understudy:retry), environment names (UNDERSTUDY_X),
 * file and directory names (understudy.json, ~/.understudy/memory.md). A token is one of these when the old name is glued to other characters by one of
 * - _ . / : ~ or a backslash. A bare "Understudy", or "Understudy's", is the name a person would read, so it is not.
 */
export function stripIdentifiers(text: string): string {
  return text.replace(/\S*[-_./\\:~]understudy\S*|\S*understudy[-_./\\:~]\S*|\bUNDERSTUDY_\w*/gi, " ");
}

/** Everything in `text` that must not be visible. `cfg` is docs/knack-ux/banned-phrases.json. */
export function findBanned(text: string, cfg: BannedConfig): Finding[] {
  const out: Finding[] = [];
  for (const p of cfg.phrases) { const m = phraseRegex(p).exec(text); if (m) out.push({ kind: "phrase", match: m[0] }); }
  for (const w of cfg.visible_words) { const m = new RegExp(`\\b${escape(w)}\\b`, "i").exec(text); if (m) out.push({ kind: "word", match: m[0] }); }
  const bare = stripIdentifiers(text);
  const old = new RegExp(`\\b${escape(cfg.visible_old_name.word)}\\b`, "i").exec(bare);
  if (old) out.push({ kind: "old name", match: old[0] });
  // The owner's earlier library. Capital A only: "alongside" in a sentence is an ordinary word.
  const along = /\bAlongside\b/.exec(bare);
  if (along) out.push({ kind: "name", match: along[0] });
  return out;
}

/** Every string value in a built object (a view model, a sentence list): the text a screen would draw from it. Keys are not text. */
export function stringsIn(value: unknown, path = "$", seen = new Set<unknown>()): { text: string; path: string }[] {
  if (typeof value === "string") return [{ text: value, path }];
  if (!value || typeof value !== "object" || seen.has(value)) return [];
  seen.add(value);
  if (Array.isArray(value)) return value.flatMap((v, i) => stringsIn(v, `${path}[${i}]`, seen));
  return Object.entries(value).flatMap(([k, v]) => stringsIn(v, `${path}.${k}`, seen));
}
