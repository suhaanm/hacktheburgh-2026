// Accessibility-first target resolver for NATIVE macOS apps (point_at and act_for_me).
// Why: a full-screen screenshot read through Gemini's 0-999 grid is only good to roughly +-20 points, which is MORE than half
// the width of a Calculator key (48 pt), so vision alone lands on the neighbouring key. macOS exposes the exact frame of
// every control, so when the model's words name an element we use that element's exact centre, and fall back to the
// vision coordinates when there is no confident match.
// Privacy: only role / title / description / AXIdentifier / frame of BUTTON-like controls are read. Text fields, secure
// fields and any "value" are never read. One short osascript call, hard timeout, depth and size limits.
// Ideas only from the Codex-style approach (AX tree first, vision as fallback); no code copied from any other project.
import { execFile } from 'node:child_process'
import type { NormBox, NormPoint } from '../../shared/protocol'
import { pointsToNorm, type DisplayBounds } from '../actuator/mapping'

export interface AxElement {
  role: string
  title: string
  desc: string
  id: string
  // Global screen POINTS (top-left origin of the primary display), exactly what System Events reports.
  x: number
  y: number
  w: number
  h: number
}

export interface AxResolved {
  el: AxElement
  // Exact frame centre, in points.
  center: { x: number; y: number }
  how: 'label' | 'snap'
  // Plain words of the element, for the policy denylist and the audit.
  text: string
  point: NormPoint
  box: NormBox
}

export const AX_TIMEOUT_MS = 1500
export const AX_MAX_ELEMENTS = 400
// A label match farther than this from where the model pointed is assumed to be a different thing with the same words.
export const MAX_MATCH_DISTANCE_PT = 260

export const axEnabled = (): boolean => process.env.ALONGSIDE_AX_RESOLVER !== '0'

// ---------- JXA: one call, batched property reads (fast), buttons only ----------
export const AX_JXA = `function run() {
  var se = Application('System Events');
  var procs = se.processes.whose({frontmost: true})();
  if (!procs.length) return '{}';
  var p = procs[0];
  var out = {app: p.name(), els: []};
  var budget = ${AX_MAX_ELEMENTS}, deadline = Date.now() + 1150;
  var CONT = {AXGroup:1,AXSplitGroup:1,AXScrollArea:1,AXToolbar:1,AXTabGroup:1,AXList:1,AXOutline:1,AXRow:1,AXCell:1,AXLayoutArea:1,AXRadioGroup:1};
  var KEEP = {AXButton:1,AXCheckBox:1,AXRadioButton:1,AXPopUpButton:1,AXMenuButton:1,AXLink:1,AXTabButton:1,AXDisclosureTriangle:1,AXSegmentedControl:1};
  function safe(f) { try { return f(); } catch (x) { return null; } }
  function walk(node, depth) {
    if (depth > 9 || budget <= 0 || Date.now() > deadline) return;
    var ui = node.uiElements;
    var roles = safe(function () { return ui.role(); });
    if (!roles) return;
    var pos = safe(function () { return ui.position(); }) || [];
    var siz = safe(function () { return ui.size(); }) || [];
    var tit = safe(function () { return ui.title(); }) || [];
    var dsc = safe(function () { return ui.description(); }) || [];
    var ids = safe(function () { return ui.attributes.byName('AXIdentifier').value(); }) || [];
    for (var i = 0; i < roles.length; i++) {
      var r = roles[i];
      if (KEEP[r] && pos[i] && siz[i]) {
        budget--;
        out.els.push({r: r, t: tit[i] || '', d: dsc[i] || '', id: ids[i] || '', x: pos[i][0], y: pos[i][1], w: siz[i][0], h: siz[i][1]});
      }
      if (CONT[r] === 1 && !KEEP[r]) walk(ui[i], depth + 1);
    }
  }
  var w = safe(function () { return p.windows[0]; });
  if (w) walk(w, 0);
  return JSON.stringify(out);
}`

export interface AxSnapshot {
  app: string
  els: AxElement[]
}

export function parseAxOutput(raw: string): AxSnapshot | null {
  let j: unknown
  try {
    j = JSON.parse(raw)
  } catch {
    return null
  }
  if (!j || typeof j !== 'object') return null
  const o = j as { app?: unknown; els?: unknown }
  if (typeof o.app !== 'string' || !Array.isArray(o.els)) return null
  const els: AxElement[] = []
  for (const e of o.els.slice(0, AX_MAX_ELEMENTS)) {
    if (!e || typeof e !== 'object') continue
    const r = e as Record<string, unknown>
    const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : NaN)
    const str = (v: unknown): string => (typeof v === 'string' ? v.slice(0, 120) : '')
    const x = num(r.x), y = num(r.y), w = num(r.w), h = num(r.h)
    if ([x, y, w, h].some(Number.isNaN) || w <= 0 || h <= 0) continue
    els.push({ role: str(r.r), title: str(r.t), desc: str(r.d), id: str(r.id), x, y, w, h })
  }
  return { app: o.app, els }
}

export function readFrontmostAx(timeoutMs = AX_TIMEOUT_MS): Promise<AxSnapshot | null> {
  if (process.platform !== 'darwin') return Promise.resolve(null)
  return new Promise((resolve) => {
    execFile('/usr/bin/osascript', ['-l', 'JavaScript', '-e', AX_JXA], { timeout: timeoutMs, killSignal: 'SIGKILL', maxBuffer: 1 << 20 }, (err, stdout) => {
      if (err) return resolve(null)
      resolve(parseAxOutput(String(stdout).trim()))
    })
  })
}

// ---------- matching (pure) ----------
const NUMBER_WORDS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine']
const SYNONYMS: Record<string, string> = {
  add: 'plus', addition: 'plus',
  subtract: 'minus', subtraction: 'minus',
  multiply: 'times', multiplication: 'times', multiplied: 'times',
  divided: 'divide', division: 'divide',
  equal: 'equals',
  dot: 'decimal',
  backspace: 'delete', remove: 'delete',
  allclear: 'clear',
}
const SYMBOLS: Record<string, string> = { '+': ' plus ', '-': ' minus ', '−': ' minus ', '–': ' minus ', '×': ' times ', '*': ' times ', '÷': ' divide ', '/': ' divide ', '=': ' equals ', '%': ' percent ', '.': ' decimal ' }
const STOP = new Set(['click', 'press', 'tap', 'select', 'choose', 'hit', 'the', 'a', 'an', 'button', 'key', 'in', 'on', 'to', 'of', 'and', 'then', 'with', 'for', 'at', 'it', 'its', 'app', 'calculator', 'window', 'icon', 'digit', 'number', 'next', 'continue', 'typing', 'type', 'using', 'now', 'sign', 'last', 'extra', 'point', 'find', 'show', 'here'])

function canon(tok: string): string {
  const w = SYNONYMS[tok] ?? tok
  const n = NUMBER_WORDS.indexOf(w)
  return n >= 0 ? String(n) : w
}

export function tokens(text: string, isId = false): string[] {
  let t = text.replace(/[‎‏]/g, '')
  if (isId) t = t.replace(/([a-z])([A-Z])/g, '$1 $2')
  // Symbols only matter when they stand alone ("click +", "the = key"), never inside words or numbers like 3.5.
  t = t.replace(/(^|\s)([+\-−–×*÷/=%.])(?=\s|$)/g, (_m, pre: string, sym: string) => `${pre}${SYMBOLS[sym] ?? ' '}`)
  const out: string[] = []
  for (const raw of t.toLowerCase().split(/[^a-z0-9]+/)) {
    if (!raw) continue
    const c = canon(raw)
    if (!isId && STOP.has(c)) continue
    out.push(c)
  }
  return out
}

const GENERIC_ID = /^(button|group|mode|view|main)$/

export function elementTokens(e: AxElement): Set<string> {
  const s = new Set<string>()
  for (const t of tokens(e.id, true)) if (!GENERIC_ID.test(t)) s.add(t)
  for (const t of tokens(e.title)) s.add(t)
  for (const t of tokens(e.desc)) s.add(t)
  return s
}

export const elementText = (e: AxElement): string => [e.title, e.desc !== 'button' ? e.desc : '', e.id].filter(Boolean).join(' ').slice(0, 120)

const centre = (e: AxElement) => ({ x: e.x + e.w / 2, y: e.y + e.h / 2 })

// Role-driven noise that is never a click target for a task: the window's own traffic lights.
const WINDOW_CHROME = /^(close|minimize|zoom|full screen) button$/

export interface MatchHint {
  // Where the vision model pointed, in points (used to break ties and to reject far-away namesakes).
  near?: { x: number; y: number }
}

// Confident label match: unique best score, and (when we know where vision pointed) not absurdly far from it.
export function matchByLabel(label: string, els: readonly AxElement[], hint: MatchHint = {}): AxElement | null {
  const want = [...new Set(tokens(label))]
  if (!want.length) return null
  const scored: Array<{ e: AxElement; score: number; dist: number }> = []
  for (const e of els) {
    if (WINDOW_CHROME.test(e.desc)) continue
    const have = elementTokens(e)
    let hit = 0
    for (const t of want) if (have.has(t)) hit++
    if (!hit) continue
    const c = centre(e)
    const dist = hint.near ? Math.hypot(c.x - hint.near.x, c.y - hint.near.y) : 0
    scored.push({ e, score: hit * 10 - (have.size - hit), dist })
  }
  if (!scored.length) return null
  scored.sort((a, b) => b.score - a.score || a.dist - b.dist)
  const best = scored[0]
  const tied = scored.filter((s) => s.score === best.score)
  // Several elements with the same words (e.g. two "Close" buttons): only trust the one nearest to where vision pointed.
  if (tied.length > 1 && !hint.near) return null
  if (hint.near && best.dist > MAX_MATCH_DISTANCE_PT) return null
  return best.e
}

// The smallest control whose frame contains the point (pure snap to the exact centre; never changes WHICH control).
export function snapToContaining(p: { x: number; y: number }, els: readonly AxElement[]): AxElement | null {
  let best: AxElement | null = null
  for (const e of els) {
    if (p.x < e.x || p.x > e.x + e.w || p.y < e.y || p.y > e.y + e.h) continue
    if (!best || e.w * e.h < best.w * best.h) best = e
  }
  return best
}

export function resolveFromElements(label: string, els: readonly AxElement[], bounds: DisplayBounds, visionNorm?: NormPoint | null): AxResolved | null {
  const near = visionNorm ? { x: bounds.x + (visionNorm.x / 1000) * bounds.width, y: bounds.y + (visionNorm.y / 1000) * bounds.height } : undefined
  let how: AxResolved['how'] = 'label'
  let el = matchByLabel(label, els, { near })
  if (!el && near) {
    el = snapToContaining(near, els)
    how = 'snap'
  }
  if (!el) return null
  const c = centre(el)
  const point = pointsToNorm(c, bounds)
  const tl = pointsToNorm({ x: el.x, y: el.y }, bounds)
  const br = pointsToNorm({ x: el.x + el.w, y: el.y + el.h }, bounds)
  return { el, center: c, how, text: elementText(el), point, box: { xmin: tl.x, ymin: tl.y, xmax: br.x, ymax: br.y } }
}

// ---------- the real thing ----------
export interface AxResolverDeps {
  read?: () => Promise<AxSnapshot | null>
  bounds?: () => Promise<DisplayBounds>
  log?: (scope: string, ...args: unknown[]) => void
}

export type AxResolve = (label: string, visionNorm?: NormPoint | null) => Promise<AxResolved | null>

export function createAxResolver(deps: AxResolverDeps = {}): AxResolve {
  const read = deps.read ?? (() => readFrontmostAx())
  const bounds =
    deps.bounds ??
    (async () => {
      const { screen } = await import('electron')
      return screen.getPrimaryDisplay().bounds
    })
  return async (label, visionNorm) => {
    if (!axEnabled()) return null
    try {
      const snap = await read()
      if (!snap || !snap.els.length) return null
      // Never resolve inside our own windows: the overlay and dock are not the target.
      if (/^(Electron|Alongside)$/i.test(snap.app)) return null
      const r = resolveFromElements(label, snap.els, await bounds(), visionNorm)
      deps.log?.('ax', `app=${snap.app} els=${snap.els.length} ${r ? `${r.how} -> "${r.text}" at ${Math.round(r.center.x)},${Math.round(r.center.y)}` : 'no confident match'}`)
      return r
    } catch {
      return null
    }
  }
}
