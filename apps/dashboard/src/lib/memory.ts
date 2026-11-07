import type { Memory, MemoryLine } from "../types";

export const SECTION_ORDER = ["Preferences", "Procedure", "Routines", "Corrections", "Skill state", "Never"] as const;

export interface ParsedMemory {
  role: string;
  revision: number;
  sections: Record<string, MemoryLine[]>;
}

const NOTE_RE = /\s*<!--\s*(.*?)\s*-->\s*$/;

/** Parse the worker's Markdown memory file. Unknown sections are kept. Ids are stable by section and position. */
export function parseMemory(markdown: string, previous?: Record<string, MemoryLine[]>): ParsedMemory {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  let role = "";
  let revision = 0;
  let i = 0;
  if (lines[0]?.trim() === "---") {
    i = 1;
    while (i < lines.length && lines[i].trim() !== "---") {
      const m = /^(\w+):\s*(.*)$/.exec(lines[i]);
      if (m && m[1] === "role") role = m[2].trim();
      if (m && m[1] === "revision") revision = Number(m[2]) || 0;
      i++;
    }
    i++;
  }
  const sections: Record<string, MemoryLine[]> = {};
  let current: string | null = null;
  const used = new Set<string>();
  for (; i < lines.length; i++) {
    const raw = lines[i];
    const h = /^##\s+(.*\S)\s*$/.exec(raw);
    if (h) {
      current = h[1];
      sections[current] = sections[current] ?? [];
      continue;
    }
    const b = /^\s*[-*]\s+(.*\S)\s*$/.exec(raw);
    if (b && current) {
      let text = b[1];
      let note: string | null = null;
      const n = NOTE_RE.exec(text);
      if (n) {
        note = n[1];
        text = text.replace(NOTE_RE, "");
      }
      text = text.trimEnd();
      const reuse = previous?.[current]?.find((l) => l.text === text && !used.has(l.id));
      const id = reuse?.id ?? `mem_${slug(current)}_${sections[current].length + 1}_${hash(text)}`;
      used.add(id);
      sections[current].push({ id, text, note });
    }
  }
  return { role, revision, sections };
}

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
function hash(s: string): string {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36).slice(0, 4);
}

export function serializeMemory(role: string, revision: number, sections: Record<string, MemoryLine[]>): string {
  const out = ["---", `role: ${role}`, `revision: ${revision}`, "---"];
  const names = [...SECTION_ORDER.filter((n) => n in sections), ...Object.keys(sections).filter((n) => !(SECTION_ORDER as readonly string[]).includes(n))];
  for (const name of names) {
    out.push(`## ${name}`);
    for (const l of sections[name]) out.push(`- ${l.text}${l.note ? `   <!-- ${l.note} -->` : ""}`);
  }
  return out.join("\n") + "\n";
}

/** Replace one line's text inside the Markdown, matching on its current text. Returns null if not found. */
export function replaceLineText(markdown: string, oldText: string, newText: string): string | null {
  const lines = markdown.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const m = /^(\s*[-*]\s+)(.*?)((?:\s*<!--.*?-->)?\s*)$/.exec(lines[i]);
    if (m && m[2].trimEnd() === oldText.trimEnd()) {
      lines[i] = `${m[1]}${newText}${m[3]}`;
      return lines.join("\n");
    }
  }
  return null;
}

export function removeLineText(markdown: string, text: string): string | null {
  const lines = markdown.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const m = /^\s*[-*]\s+(.*?)(?:\s*<!--.*?-->)?\s*$/.exec(lines[i]);
    if (m && m[1].trimEnd() === text.trimEnd()) {
      lines.splice(i, 1);
      return lines.join("\n");
    }
  }
  return null;
}

export function toMemory(path: string, markdown: string, previous?: Record<string, MemoryLine[]>): Memory {
  const p = parseMemory(markdown, previous);
  return { path, revision: p.revision, markdown, sections: p.sections };
}

/** Find which section a line id belongs to. */
export function findLine(sections: Record<string, MemoryLine[]>, id: string): { section: string; line: MemoryLine } | null {
  for (const [section, ls] of Object.entries(sections)) {
    const line = ls.find((l) => l.id === id);
    if (line) return { section, line };
  }
  return null;
}

const CAPTURE_RE = /^Capture:/i;

/** Capture is on when a Preferences line says "Capture: times only". It is only that line. */
export function captureOn(sections: Record<string, MemoryLine[]>): boolean {
  return (sections.Preferences ?? []).some((l) => CAPTURE_RE.test(l.text.trim()) && /times only/i.test(l.text));
}

/** Turn capture on or off by editing the one line in the Markdown. Returns the new Markdown. */
export function setCapture(markdown: string, on: boolean): string {
  const lines = markdown.replace(/\n$/, "").split("\n");
  const isCap = (l: string) => /^\s*[-*]\s+Capture:/i.test(l);
  const kept = lines.filter((l) => !isCap(l));
  if (!on) return kept.join("\n") + "\n";
  const h = kept.findIndex((l) => /^##\s+Preferences\s*$/.test(l));
  if (h < 0) return [...kept, "## Preferences", "- Capture: times only"].join("\n") + "\n";
  let end = h + 1;
  while (end < kept.length && !/^##\s/.test(kept[end])) end++;
  // Insert after the last non-blank line of the Preferences section.
  let at = end;
  while (at > h + 1 && kept[at - 1].trim() === "") at--;
  kept.splice(at, 0, "- Capture: times only");
  return kept.join("\n") + "\n";
}
