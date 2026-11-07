// The scanner behind tests/brand-guard.test.ts: finds the old product names ("Understudy", "Alongside") in text a person can read.
// Pure: it takes source text and returns hits; the test walks the trees. Comments are not visible to anyone, so they are removed first.
// What stays after that is string literals and JSX text, which is where visible copy lives.
//
// Allowed on purpose (internal names stay, owner decision of 7 Nov 2026): HTTP header names (X-Understudy-Actor), anything that is not the
// capitalised word (env vars UNDERSTUDY_*, ALONGSIDE_*, paths such as ~/.understudy, module names, identifiers such as understudyHud or
// createUnderstudyCore), and internal log lines (a line that calls a logger). Everything else that is shown must say the product name.
import fs from 'node:fs'
import path from 'node:path'

export interface Hit {
  file: string
  line: number
  text: string
}

/** The capitalised old names. A word boundary on both sides keeps identifiers (createUnderstudyCore, understudyHud) out. */
export const OLD_NAME = /\b(Understudy|Alongside)\b/g

/** Removes // and block comments, leaving string literals (including URLs inside them) alone. Line breaks are kept so line numbers hold. */
export function stripComments(src: string): string {
  let out = ''
  let i = 0
  let quote: string | null = null
  while (i < src.length) {
    const c = src[i]
    const n = src[i + 1]
    if (quote) {
      out += c
      if (c === '\\') {
        out += n ?? ''
        i += 2
        continue
      }
      // A single- or double-quoted string ends at the line end (an apostrophe in JSX text is not a quote); a template may span lines.
      if (c === quote || (c === '\n' && quote !== '`')) quote = null
      i++
      continue
    }
    if (c === '/' && n === '/') {
      while (i < src.length && src[i] !== '\n') i++
      continue
    }
    if (c === '/' && n === '*') {
      i += 2
      while (i < src.length && !(src[i] === '*' && src[i + 1] === '/')) {
        if (src[i] === '\n') out += '\n'
        i++
      }
      i += 2
      continue
    }
    if (c === '"' || c === "'" || c === '`') quote = c
    out += c
    i++
  }
  return out
}

/** HTML comments too, for .html files. */
const stripHtmlComments = (src: string): string => src.replace(/<!--[\s\S]*?-->/g, (m) => m.replace(/[^\n]/g, ''))

/** Lines that only write to a log are internal: they may keep the old name. */
const LOG_LINE = /\b(console\.(log|warn|error|info|debug)|log|ctx\.log|deps\.log|logger)\s*\(/

/** The allow-list: the part of a line that may hold the old name. Each entry says why. */
export const ALLOWED: { pattern: RegExp; why: string }[] = [
  { pattern: /X-Understudy-[A-Za-z-]+/g, why: 'HTTP header names are part of the service contract' },
  { pattern: /`?[\w./~-]*\.understudy[\w./-]*`?/g, why: 'file paths' },
]

export function scanSource(src: string, file: string, kind: 'code' | 'html' = 'code'): Hit[] {
  const clean = kind === 'html' ? stripHtmlComments(src) : stripComments(src)
  const hits: Hit[] = []
  clean.split('\n').forEach((raw, idx) => {
    if (kind === 'code' && LOG_LINE.test(raw)) return
    let line = raw
    for (const a of ALLOWED) line = line.replace(a.pattern, '')
    OLD_NAME.lastIndex = 0
    if (OLD_NAME.test(line)) hits.push({ file, line: idx + 1, text: raw.trim().slice(0, 160) })
  })
  return hits
}

const SKIP_DIRS = new Set(['node_modules', 'out', 'dist', '.vite', 'harness', 'fixtures', 'qa', 'spikes', 'tests', '__snapshots__'])

/** Source files under a root that a person could see text from: .ts .tsx .html .css, not tests and not fixtures. */
export function listVisibleSources(root: string): string[] {
  const out: string[] = []
  const walk = (dir: string): void => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        if (!SKIP_DIRS.has(entry.name)) walk(path.join(dir, entry.name))
        continue
      }
      if (/\.(test|spec)\.tsx?$/.test(entry.name) || /\.test-util\.ts$/.test(entry.name)) continue
      if (/\.(tsx?|html|css)$/.test(entry.name) && !entry.name.endsWith('.d.ts')) out.push(path.join(dir, entry.name))
    }
  }
  walk(root)
  return out
}

export function scanTree(root: string, relativeTo: string): Hit[] {
  const hits: Hit[] = []
  for (const file of listVisibleSources(root)) {
    const rel = path.relative(relativeTo, file)
    hits.push(...scanSource(fs.readFileSync(file, 'utf8'), rel, file.endsWith('.html') ? 'html' : 'code'))
  }
  return hits
}
