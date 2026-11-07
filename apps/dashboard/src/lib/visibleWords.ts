// A scanner for the words a person can see or a screen reader reads, in source files and fixtures. Pure (it only takes text), so it is tested
// and used by words.test.ts, which fails the build if a banned word shows up in anything visible.
//
// What counts as visible: string literals (including the static parts of template strings), JSX text, and string values in JSON fixtures.
// What does not: comments, identifiers, property names, file names. A literal that is exactly the bare word (an enum value such as
// `source: "demo"`) is code, not text, so it is skipped; a word glued to others by `_` or camelCase has no word boundary and never matches.

export interface Hit { text: string; line: number }

const PRIOR_REGEX_OK = new Set(["(", ",", "=", ":", "[", "!", "&", "|", "?", "{", "}", ";", "+", "-", "*", "%", "<", ">", "~", "^"]);

/** The string literals and the code left over (strings blanked, comments removed). Handles ', ", ` with ${ } nesting, // and block comments, and regex literals. */
export function tokenise(src: string): { strings: Hit[]; code: string } {
  const strings: Hit[] = [];
  let code = "";
  let line = 1;
  let i = 0;
  const n = src.length;
  let lastSig = "";

  const readTemplate = (): void => {
    // At the character after the opening backtick. Static parts are strings; ${ ... } is code, scanned recursively by the main loop.
    let buf = "";
    let startLine = line;
    while (i < n) {
      const c = src[i];
      if (c === "\\") { buf += src.slice(i, i + 2); if (src[i + 1] === "\n") line++; i += 2; continue; }
      if (c === "`") { strings.push({ text: buf, line: startLine }); i++; return; }
      if (c === "$" && src[i + 1] === "{") {
        strings.push({ text: buf, line: startLine }); buf = "";
        i += 2;
        let depth = 1;
        const exprStart = i;
        // Find the matching brace, skipping nested strings and templates, then scan the expression as code.
        while (i < n && depth > 0) {
          const d = src[i];
          if (d === "{") depth++;
          else if (d === "}") depth--;
          else if (d === '"' || d === "'") { const q = d; i++; while (i < n && src[i] !== q) { if (src[i] === "\\") i++; i++; } }
          else if (d === "`") { i++; let t = 1; while (i < n && t > 0) { if (src[i] === "\\") i++; else if (src[i] === "`") t--; i++; } i--; }
          i++;
        }
        const inner = tokenise(src.slice(exprStart, i - 1));
        for (const s of inner.strings) strings.push({ text: s.text, line: startLine + s.line - 1 });
        code += " " + inner.code + " ";
        startLine = line;
        continue;
      }
      if (c === "\n") line++;
      buf += c;
      i++;
    }
  };

  while (i < n) {
    const c = src[i];
    const two = src.slice(i, i + 2);
    if (two === "//") { while (i < n && src[i] !== "\n") i++; continue; }
    if (two === "/*") { i += 2; while (i < n && src.slice(i, i + 2) !== "*/") { if (src[i] === "\n") line++; i++; } i += 2; continue; }
    if (c === '"' || c === "'") {
      const q = c; const startLine = line; i++;
      let buf = "";
      while (i < n && src[i] !== q) {
        if (src[i] === "\\") { buf += src.slice(i, i + 2); i += 2; continue; }
        if (src[i] === "\n") { break; }
        buf += src[i++];
      }
      i++;
      strings.push({ text: buf, line: startLine });
      code += '""';
      lastSig = '"';
      continue;
    }
    if (c === "`") { i++; readTemplate(); code += '""'; lastSig = '"'; continue; }
    if (c === "/" && (lastSig === "" || PRIOR_REGEX_OK.has(lastSig) || /^[a-z]+$/.test(lastSig))) {
      // A regex literal (division follows an identifier, a number or a closing bracket).
      if (!/[A-Za-z0-9_$)\]]/.test(lastSig) || /^(return|typeof|case|in|of)$/.test(lastSig)) {
        i++;
        let inClass = false;
        while (i < n && (src[i] !== "/" || inClass)) { if (src[i] === "\\") i++; else if (src[i] === "[") inClass = true; else if (src[i] === "]") inClass = false; else if (src[i] === "\n") break; i++; }
        i++;
        while (i < n && /[a-z]/.test(src[i])) i++;
        code += "/r/";
        lastSig = ")";
        continue;
      }
    }
    if (c === "\n") line++;
    code += c;
    if (!/\s/.test(c)) lastSig = c;
    i++;
  }
  return { strings, code };
}

/** JSX text between tags, from the code with strings blanked: `<p>text {x} more</p>` gives "text", "more". Over-matches harmlessly (a stray `>` and `<` in code). */
export function jsxTexts(code: string): Hit[] {
  const out: Hit[] = [];
  const re = />([^<>{}=;]+)(?=<|\{)/g;
  const lineAt = (idx: number) => code.slice(0, idx).split("\n").length;
  let m: RegExpExecArray | null;
  while ((m = re.exec(code))) {
    const t = m[1].replace(/\s+/g, " ").trim();
    if (/[A-Za-z]{2,}/.test(t)) out.push({ text: t, line: lineAt(m.index) });
  }
  // Text on its own lines inside an element (multi-line paragraphs).
  const lines = code.split("\n");
  lines.forEach((ln, idx) => { const t = ln.trim(); if (/^[A-Z][A-Za-z ,.'’()-]{12,}$/.test(t) && !/[=;{}()]$/.test(t)) out.push({ text: t, line: idx + 1 }); });
  return out;
}

/** The banned word as a whole word, any case. `demo` glued to other word characters (demoMode, r_demo_1) is an identifier and does not count. */
export const bannedWord = (word: string): RegExp => new RegExp(`\\b${word}\\b`, "i");

/** A literal that is only the bare word is an enum value in code, not text. */
const isBareWord = (text: string, word: string): boolean => text.trim().toLowerCase() === word.toLowerCase();

/** Visible-text hits of `word` in a TS or TSX source file. */
export function scanSource(src: string, word = "demo"): Hit[] {
  const re = bannedWord(word);
  const { strings, code } = tokenise(src);
  const hits: Hit[] = [];
  for (const s of strings) if (re.test(s.text) && !isBareWord(s.text, word) && !looksLikePath(s.text)) hits.push(s);
  for (const j of jsxTexts(code)) if (re.test(j.text)) hits.push(j);
  return hits;
}

/** A path or id (apps/demo-stage/index.html, demo-data), not prose: no spaces and a slash or dot or dash. */
export const looksLikePath = (t: string): boolean => !/\s/.test(t) && /[/.]|-/.test(t);

/** Visible-text hits in a parsed JSON value: every string value, with its path. Keys are not text. */
export function scanJson(value: unknown, word = "demo", path = "$"): { text: string; path: string }[] {
  const re = bannedWord(word);
  if (typeof value === "string") return re.test(value) && !isBareWord(value, word) && !looksLikePath(value) ? [{ text: value, path }] : [];
  if (Array.isArray(value)) return value.flatMap((v, k) => scanJson(v, word, `${path}[${k}]`));
  if (value && typeof value === "object") return Object.entries(value).flatMap(([k, v]) => scanJson(v, word, `${path}.${k}`));
  return [];
}
