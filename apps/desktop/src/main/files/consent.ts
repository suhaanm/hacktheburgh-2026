// Which folders may be indexed, and which files inside them. Pure node (no electron) so it is unit-testable.
// The model never supplies a path: folders come from a native dialog in main, and every use re-checks them here.
import fs from 'node:fs'
import path from 'node:path'
import { FILES_LIMITS } from '../../shared/files'

export const TEXT_EXTS = new Set(['.txt', '.md', '.markdown', '.csv', '.json', '.html', '.htm', '.rtf'])
export const GEMINI_EXTS = new Set(['.pdf', '.png', '.jpg', '.jpeg', '.webp'])
export const SUPPORTED_EXTS = new Set([...TEXT_EXTS, ...GEMINI_EXTS])

// Exact matches only (their children are fine, e.g. /Volumes/Photos or the macOS temp folders).
const BROAD_EXACT = new Set(['/', '/Users', '/Volumes', '/private', '/private/var', '/var', '/tmp', '/home', '/Network'])
// Anything at or inside these.
const SYSTEM_PREFIXES = [
  '/System',
  '/Library',
  '/usr',
  '/bin',
  '/sbin',
  '/etc',
  '/dev',
  '/cores',
  '/opt',
  '/Applications',
  '/private/etc',
  '/private/var/db',
  '/private/var/root',
  '/private/var/log',
]
// Folder names that hold credentials, browser profiles or app data, wherever they sit.
const SENSITIVE_DIR = /^(keychains?|\.?ssh|\.?gnupg|\.?aws|\.?kube|cookies|local storage|indexeddb|login data|user data)$/i
const SENSITIVE_PATH_PARTS = /(google[\\/]chrome|mozilla[\\/]firefox|microsoft edge|brave-?browser|1password|bitwarden|keepass|lastpass|application support|\.gnupg|\.ssh)/i
// File names that are probably secrets, whatever the extension.
const SENSITIVE_FILE =
  /(^|[^a-z])(passwords?|passwd|passphrase|secrets?|credentials?|private[-_ ]?key|id_(rsa|ed25519|ecdsa)|keychain|recovery[-_ ]?(codes?|key)|2fa|backup[-_ ]?codes?|wallet|seed[-_ ]?phrase)([^a-z]|$)|\.(pem|key|p12|pfx|keystore|kdbx|ovpn)$|^\.env/i
const SKIP_DIRS = new Set(['node_modules', '__pycache__', 'venv', 'site-packages', 'build', 'dist', 'target'])
const BUNDLE_EXT = /\.(app|photoslibrary|xcodeproj|xcworkspace|bundle|framework|lproj|pkg|dmg|sparsebundle|noindex|rtfd)$/i

export type FolderCheck = { ok: true; real: string; name: string } | { ok: false; error: string }

const TOO_BROAD = 'That folder is too broad. Please choose a smaller folder, like one of your document folders.'
const PRIVATE = 'That folder holds private or system files, so I will not look in it. Please choose another.'

const isInside = (child: string, parent: string): boolean => child === parent || child.startsWith(parent.endsWith(path.sep) ? parent : parent + path.sep)

export function checkFolder(input: string, opts: { home: string; extraBlocked?: string[] }): FolderCheck {
  if (typeof input !== 'string' || !input.trim() || input.includes('\0')) return { ok: false, error: 'I could not use that folder.' }
  if (!path.isAbsolute(input)) return { ok: false, error: 'I could not use that folder.' }
  let real: string
  let home: string
  try {
    real = fs.realpathSync(input)
    home = fs.realpathSync(opts.home)
    if (!fs.statSync(real).isDirectory()) return { ok: false, error: 'That is not a folder.' }
    fs.accessSync(real, fs.constants.R_OK)
  } catch {
    return { ok: false, error: 'I could not open that folder.' }
  }

  if (BROAD_EXACT.has(real) || real === home || isInside(home, real)) return { ok: false, error: TOO_BROAD }
  if (SYSTEM_PREFIXES.some((p) => isInside(real, p))) return { ok: false, error: PRIVATE }
  if (isInside(real, path.join(home, 'Library'))) return { ok: false, error: PRIVATE }
  for (const blocked of opts.extraBlocked ?? []) {
    try {
      const b = fs.realpathSync(blocked)
      if (isInside(real, b) || isInside(b, real)) return { ok: false, error: PRIVATE }
    } catch {
      // A blocked path that does not exist cannot overlap.
    }
  }
  const rel = isInside(real, home) ? path.relative(home, real) : real
  const parts = rel.split(path.sep).filter(Boolean)
  if (parts.some((p) => p.startsWith('.') || SENSITIVE_DIR.test(p))) return { ok: false, error: PRIVATE }
  if (SENSITIVE_PATH_PARTS.test(rel)) return { ok: false, error: PRIVATE }
  return { ok: true, real, name: path.basename(real) || real }
}

export interface ScannedFile {
  abs: string
  folder: string
  rel: string
  name: string
  ext: string
  size: number
  mtimeMs: number
}

export type SkipReason = 'hidden' | 'too_big' | 'empty' | 'unsupported' | 'sensitive_name' | 'over_limit' | 'unreadable'

export interface ScanResult {
  files: ScannedFile[]
  skipped: Record<SkipReason, number>
  truncated: boolean
}

const emptySkips = (): Record<SkipReason, number> => ({ hidden: 0, too_big: 0, empty: 0, unsupported: 0, sensitive_name: 0, over_limit: 0, unreadable: 0 })

export interface ScanOptions {
  maxFiles?: number
  maxTotalBytes?: number
  maxFileBytes?: number
  // Absolute paths never to descend into (the index itself).
  exclude?: string[]
}

// Breadth-first so the shallow, usually most useful files win when a cap is hit. Symlinks are never followed.
export function scanFolders(folders: string[], opts: ScanOptions = {}): ScanResult {
  const maxFiles = opts.maxFiles ?? FILES_LIMITS.maxFiles
  const maxTotal = opts.maxTotalBytes ?? FILES_LIMITS.maxTotalBytes
  const maxFile = opts.maxFileBytes ?? FILES_LIMITS.maxFileBytes
  const exclude = (opts.exclude ?? []).map((p) => {
    try {
      return fs.realpathSync(p)
    } catch {
      return p
    }
  })
  const out: ScannedFile[] = []
  const skipped = emptySkips()
  let total = 0
  let truncated = false
  const seen = new Set<string>()

  for (const folder of folders) {
    const queue: string[] = [folder]
    while (queue.length) {
      const dir = queue.shift() as string
      let entries: fs.Dirent[]
      try {
        entries = fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))
      } catch {
        skipped.unreadable++
        continue
      }
      for (const entry of entries) {
        const abs = path.join(dir, entry.name)
        if (entry.name.startsWith('.')) {
          skipped.hidden++
          continue
        }
        if (entry.isSymbolicLink()) continue
        if (entry.isDirectory()) {
          if (SKIP_DIRS.has(entry.name) || BUNDLE_EXT.test(entry.name) || SENSITIVE_DIR.test(entry.name)) continue
          if (exclude.some((e) => isInside(abs, e))) continue
          queue.push(abs)
          continue
        }
        if (!entry.isFile()) continue
        const ext = path.extname(entry.name).toLowerCase()
        if (!SUPPORTED_EXTS.has(ext)) {
          skipped.unsupported++
          continue
        }
        if (SENSITIVE_FILE.test(entry.name)) {
          skipped.sensitive_name++
          continue
        }
        if (seen.has(abs)) continue
        let st: fs.Stats
        try {
          st = fs.lstatSync(abs)
        } catch {
          skipped.unreadable++
          continue
        }
        if (!st.isFile()) continue
        if (st.size === 0) {
          skipped.empty++
          continue
        }
        if (st.size > maxFile) {
          skipped.too_big++
          continue
        }
        if (out.length >= maxFiles || total + st.size > maxTotal) {
          skipped.over_limit++
          truncated = true
          continue
        }
        seen.add(abs)
        total += st.size
        out.push({ abs, folder, rel: path.relative(folder, abs), name: entry.name, ext, size: st.size, mtimeMs: Math.round(st.mtimeMs) })
      }
    }
  }
  return { files: out, skipped, truncated }
}

export const skippedTotal = (s: Record<SkipReason, number>): number => Object.values(s).reduce((a, b) => a + b, 0)

// Re-check right before reading: still a plain file, not a symlink, not grown past the cap.
export function stillReadable(file: ScannedFile, maxFileBytes = FILES_LIMITS.maxFileBytes): boolean {
  try {
    const st = fs.lstatSync(file.abs)
    return st.isFile() && !st.isSymbolicLink() && st.size > 0 && st.size <= maxFileBytes
  } catch {
    return false
  }
}
