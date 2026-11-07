// Cue storyboard: every state Cue can be in, rendered the way the worker sees it, over a stand-in page. Nothing here is a mock of Cue: the
// decisions are the parser's fixtures, they run through the real state machine (main/cue/machine.ts), the ring and the ghost cursor are drawn
// by the real overlay scene, the chip and the card by the real panel, placed by the real placement function. The page has a state picker
// (ui=1) and the panel is live: click the chip, press 1 to 4, press Escape.
//   storyboard.html?state=<id>&theme=light|dark[&ui=1][&still=1]
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactElement } from 'react'
import { createRoot } from 'react-dom/client'
import '../../design/overlay-fonts.css'
import '../card/cue.css'
import type { Annotation } from '../../../shared/protocol'
import { FIXTURES, BOX, type Box } from '../../../main/cue/fixtures'
import type { CueCardAction, CueView } from '../../../main/cue/ipc'
import { INITIAL_MACHINE, reduce, type Effect, type MachineEvent, type MachineState } from '../../../main/cue/machine'
import type { Policy } from '../../../main/cue/guards'
import { CARD_SIDES, CHIP_SIDES, normBoxToRect, placeWindow, type Rect } from '../../../main/cue/place'
import { CUE_TOKENS } from '../../../main/cue/tokens'
import { parseCueDecision } from '../../../main/cue/types'
import { annotationStyle, type AnnotationStyle } from '../../design/annotation-style'
import { planFlight } from '../../overlay/flight'
import { normToPx } from '../../overlay/geometry'
import { OverlayScene } from '../../overlay/OverlayScene'
import { EMPTY_OVERLAY_STATE, reduceOverlay, type OverlayState } from '../../overlay/store'
import { CuePanel } from '../card/CuePanel'
import { StandIn } from './StandIn'

declare global {
  interface Window {
    __cueReady?: boolean
    __cueStates?: string[]
    // For the screenshot script's layout checks: the target the panel must keep clear of (px), and the work area.
    __cueDebug?: { target: Rect | null; work: Rect; cover?: number; freeExists?: boolean | null }
  }
}

type Step = { fixture: string; patch?: Record<string, unknown> } | { event: MachineEvent }
interface Story {
  label: string
  steps: Step[]
  // Freeze the ghost cursor at the landing (the press echo).
  ghost?: 'press'
  // On a narrow screen the page is scrolled down this far, so that the step's target is on screen.
  scroll?: number
}

const L = (level: number) => ({ why: { ...(FIXTURES['cue-t2-l2'] as { why: object }).why, level } })

export const STORIES: Record<string, Story> = {
  idle: { label: 'Nothing (the default)', steps: [] },
  confirm: { label: 'Confirm: a silent tick', steps: [{ fixture: 'confirm' }] },
  't1-l3': { label: 'Tier 1, level 3: thin ring only', steps: [{ fixture: 'cue-t1-l3' }] },
  't2-l2': { label: 'Tier 2, level 2: ring and chip', steps: [{ fixture: 'cue-t2-l2' }] },
  't2-l1': { label: 'Tier 2, level 1: ring, chip, step pill', steps: [{ fixture: 'cue-t2-l1' }] },
  't2-l3-regular': { label: 'Tier 1, level 2: regular ring only (compare with level 3)', steps: [{ fixture: 'cue-t1-l3', patch: L(2) }] },
  't3-ghost': { label: 'Tier 3: ghost cursor shows the move', steps: [{ fixture: 'cue-t3' }], ghost: 'press', scroll: 330 },
  't4-whisper': { label: 'Tier 4: whisper (voice; the screen is tier 2)', steps: [{ fixture: 'cue-t4' }], scroll: 330 },
  'chip-only': { label: 'A chip with nothing to ring', steps: [{ fixture: 'cue-no-target' }] },
  'why-open': { label: '"Why this?" open', steps: [{ fixture: 'cue-t2-l2' }, { event: { type: 'why', open: true } }] },
  'why-open-l1': { label: '"Why this?" open at level 1 (pill)', steps: [{ fixture: 'cue-t2-l1' }, { event: { type: 'why', open: true } }] },
  'show-me': { label: '"Show me" played', steps: [{ fixture: 'cue-t2-l2' }, { event: { type: 'show_me' } }], ghost: 'press' },
  'ask-3': { label: 'Question, 3 options', steps: [{ fixture: 'ask-3' }] },
  'ask-4': { label: 'Question, 4 options, nothing to anchor to', steps: [{ fixture: 'ask-4' }] },
  'ask-2': { label: 'Question, 2 options', steps: [{ fixture: 'ask-2' }] },
  'ask-answered': { label: 'Answered: the card collapsed into a chip', steps: [{ fixture: 'ask-3' }, { event: { type: 'answer', id: 'cliff_a' } }] },
  offer: { label: 'Offer: want a hand?', steps: [{ fixture: 'offer' }] },
  stale: { label: 'Stale target: the ring is gone at once', steps: [{ fixture: 'cue-t2-l2' }, { event: { type: 'stale' } }] },
}

const POLICY: Policy = { enabled: true, proactivity: 'balanced', quietUntil: null, pausedUntil: null, killed: false, suppressed: null }
const T0 = 1_000_000

const nominalKey = (box: unknown): string | null => {
  if (!Array.isArray(box)) return null
  return Object.entries(BOX).find(([, b]) => b.every((n, i) => n === box[i]))?.[0] ?? null
}

// A fixture's nominal box is replaced by where the stand-in page really has that element at this size.
function remap(raw: unknown, boxes: Record<string, Box>): unknown {
  const o = raw as { target?: { box_2d?: unknown } }
  const key = nominalKey(o.target?.box_2d)
  if (!key || !boxes[key]) return raw
  return { ...o, target: { ...o.target, box_2d: boxes[key] } }
}

interface Run {
  machine: MachineState
  effects: Effect[]
}

function runSteps(steps: Step[], boxes: Record<string, Box>, now: number): Run {
  let machine = INITIAL_MACHINE
  const effects: Effect[] = []
  const feed = (ev: MachineEvent): void => {
    const r = reduce(machine, ev, { now, policy: POLICY, chord: '⌥' })
    machine = r.state
    effects.push(...r.effects)
  }
  for (const s of steps) {
    if ('fixture' in s) feed({ type: 'decision', decision: parseCueDecision({ ...(remap(FIXTURES[s.fixture], boxes) as object), ...(s.patch ?? {}) }) })
    else feed(s.event)
  }
  return { machine, effects }
}

const lastView = (effects: Effect[]): CueView => {
  for (let i = effects.length - 1; i >= 0; i--) {
    const e = effects[i]
    if (e.type === 'panel') return e.view
  }
  return null
}

// The overlay's own reducer applies what the machine asked of it.
function overlayOf(effects: Effect[], style: AnnotationStyle, viewport: { width: number; height: number }): OverlayState {
  let s = EMPTY_OVERLAY_STATE
  const ctx = { now: 0, viewport, style }
  for (const e of effects) {
    if (e.type !== 'overlay') continue
    if (e.clear.length) s = reduceOverlay(s, { type: 'clear', ids: e.clear }, ctx)
    if (e.show.length) s = reduceOverlay(s, { type: 'show', annotations: e.show }, ctx)
  }
  // Marks that were cleared are gone in a still.
  return { ...s, annotations: s.annotations.filter((a) => a.exitingAt === null) }
}

// The ring's `weight: 'light'` is a field the overlay does not know yet (CONTRACT-CHANGE sent): this is what it should look like, so it can be judged.
// Core 1.25 px (regular 2), keylines 0.75 px (regular 1), the outer halo outline at half strength, corner ticks at 80 percent.
export function lightRingStyle(base: AnnotationStyle): AnnotationStyle {
  const core = 1.25
  const key = 0.75
  return { ...base, stroke: { ...base.stroke, core, casing: core + 2 * key, halo: core + 4 * key }, ring: { ...base.ring, ticks: { arm: base.ring.ticks.arm * 0.8 }, halo: { ...base.ring.halo, opacity: base.ring.halo.opacity * 0.5 } } }
}

function Storyboard(): ReactElement {
  const q = new URLSearchParams(location.search)
  const stateId = q.get('state') ?? 't2-l2'
  const dark = q.get('theme') === 'dark'
  const ui = q.get('ui') === '1'
  const still = q.get('still') !== '0'
  const [id, setId] = useState(stateId in STORIES ? stateId : 't2-l2')
  const [theme, setTheme] = useState(dark)
  const viewport = useMemo(() => ({ width: window.innerWidth, height: window.innerHeight }), [])
  const display: Rect = { x: 0, y: 0, w: viewport.width, h: viewport.height }
  // The work area of a Mac screen: below the menu bar, above the Dock.
  const work: Rect = { x: 0, y: 24, w: viewport.width, h: viewport.height - 24 - 76 }

  const [boxes, setBoxes] = useState<Record<string, Box> | null>(null)
  // What the browser extension would report about the page: the rectangles of its visible text and controls (no text), here read from the stand-in.
  const [content, setContent] = useState<Rect[]>([])
  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme ? 'dark' : 'light'
    const found: Record<string, Box> = {}
    for (const el of Array.from(document.querySelectorAll<HTMLElement>('[data-cue-target]'))) {
      const r = el.getBoundingClientRect()
      found[el.dataset.cueTarget as string] = [(r.top / viewport.height) * 1000, (r.left / viewport.width) * 1000, (r.bottom / viewport.height) * 1000, (r.right / viewport.width) * 1000].map((n) => Math.round(n * 10) / 10) as Box
    }
    setBoxes(found)
    setContent(Array.from(document.querySelectorAll<HTMLElement>('[data-content]')).map((el) => { const r = el.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height } }))
  }, [theme, viewport])

  const [run, setRun] = useState<Run>({ machine: INITIAL_MACHINE, effects: [] })
  useEffect(() => {
    if (boxes) setRun(runSteps(STORIES[id].steps, boxes, T0))
  }, [id, boxes])

  const dispatch = useCallback((ev: MachineEvent) => {
    setRun((prev) => {
      const r = reduce(prev.machine, ev, { now: still ? T0 : Date.now(), policy: POLICY, chord: '⌥' })
      return { machine: r.state, effects: [...prev.effects, ...r.effects] }
    })
  }, [still])
  const onAction = useCallback(
    (a: CueCardAction) => {
      switch (a.type) {
        case 'answer':
          return dispatch({ type: 'answer', id: a.id })
        case 'other':
          return dispatch({ type: 'answer', id: 'other' })
        case 'dismiss':
          return dispatch({ type: 'dismiss', how: 'esc' })
        case 'why':
          return dispatch({ type: 'why', open: a.open })
        case 'show_me':
          return dispatch({ type: 'show_me' })
        case 'know_this':
          return dispatch({ type: 'know_this' })
        case 'offer':
          return dispatch({ type: 'offer', yes: a.yes })
        case 'touch':
          return dispatch({ type: 'touch' })
      }
    },
    [dispatch],
  )

  const view = useMemo(() => lastView(run.effects), [run.effects])
  const base = useMemo(() => annotationStyle({ bigAnnotations: false, highContrast: false }, { dark: theme }), [theme])
  const marks = useMemo(() => overlayOf(run.effects, base, viewport), [run.effects, base, viewport])
  const light = marks.annotations.some((a) => a.annotation.kind === 'ring' && (a.annotation as { weight?: string }).weight === 'light')
  const style = useMemo(() => (light ? lightRingStyle(base) : base), [light, base])

  // Where the ghost cursor is frozen in a still: landed, with the press echo.
  const freeze = useMemo(() => {
    const g = marks.annotations.find((a) => a.annotation.kind === 'ghostCursor')?.annotation
    if (!g || g.kind !== 'ghostCursor' || !still) return null
    const path = g.path.length === 1 ? [{ x: 430, y: 560 }, ...g.path] : g.path // from where the worker's mouse rests
    const plan = planFlight(path.map((p) => normToPx(p, viewport)), style.ghostCursor.flight, { viewport })
    const lastSeg = plan.segments[plan.segments.length - 1]
    return plan.totalMs - lastSeg.holdMs + 120 + style.ghostCursor.press.durationMs * 0.35
  }, [marks, still, style, viewport])
  const ghostState = useMemo((): OverlayState => {
    // The overlay controller gives a one-point ghost path a start at the mouse; the storyboard does the same.
    return {
      ...marks,
      annotations: marks.annotations.map((a) => (a.annotation.kind === 'ghostCursor' && a.annotation.path.length === 1 ? { ...a, annotation: { ...a.annotation, path: [{ x: 430, y: 560 }, ...a.annotation.path] } as Annotation } : a)),
    }
  }, [marks])

  // The panel: placed beside the target (never over it), measured by the page itself.
  const [size, setSize] = useState<{ w: number; h: number } | null>(null)
  const onSize = useCallback((s: { w: number; h: number }) => setSize((p) => (p && p.w === s.w && p.h === s.h ? p : s)), [])
  const cardRect = useRef<Rect | null>(null)
  const placement = useMemo(() => {
    if (!view || !size) return null
    // The chip that is the card's collapsed answer stays where the card was.
    const keep = [...run.effects].reverse().find((e) => e.type === 'panel')
    if (keep && keep.type === 'panel' && keep.keep) {
      // In a still the card was never on screen: the chip goes where the card of this question would have been.
      const where = cardRect.current ?? placeWindow({ w: CUE_TOKENS.card.width + 12, h: 198 }, keep.anchor ? normBoxToRect(keep.anchor, display) : null, work, { kind: 'card', prefer: CARD_SIDES, gap: CUE_TOKENS.card.gap, content }).rect
      return { side: 'corner' as const, rect: { ...where, w: size.w, h: size.h } }
    }
    const anchor = (() => {
      for (let i = run.effects.length - 1; i >= 0; i--) {
        const e = run.effects[i]
        if (e.type === 'panel') return e.anchor
      }
      return null
    })()
    const target = anchor ? normBoxToRect(anchor, display) : null
    const card = view.mode !== 'chip'
    const placed = placeWindow(size, target, work, { kind: card ? 'card' : 'chip', prefer: card ? CARD_SIDES : CHIP_SIDES, gap: card ? CUE_TOKENS.card.gap : CUE_TOKENS.chip.gap, anchorPoint: { x: viewport.width * 0.46, y: viewport.height * 0.5 }, content })
    window.__cueDebug = { target, work, cover: placed.cover, freeExists: placed.freeExists }
    if (card) cardRect.current = placed.rect
    return placed
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, size, run.effects, content])

  // A ring or a tick with no panel beside it still has a target, for the screenshot script's close-up.
  useEffect(() => {
    if (view) return
    const m = marks.annotations.map((a) => a.annotation).find((a) => a.kind === 'ring' || a.kind === 'tick')
    window.__cueDebug = { target: m && (m.kind === 'ring' || m.kind === 'tick') ? normBoxToRect(m.box, display) : null, work }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, marks])

  useEffect(() => {
    if (!boxes) return
    const t = setTimeout(() => {
      void document.fonts.ready.then(() => {
        window.__cueReady = true
      })
    }, 350)
    return () => clearTimeout(t)
  }, [boxes, id, theme, size])
  window.__cueStates = Object.keys(STORIES)

  return (
    <div style={{ position: 'absolute', inset: 0 }}>
      <StandIn dark={theme} scroll={STORIES[id].scroll ?? 0} />
      <OverlayScene state={ghostState} viewport={viewport} style={style} captionsEnabled={false} freezeGhostMs={freeze} />
      <div style={{ position: 'absolute', left: placement?.rect.x ?? 0, top: placement?.rect.y ?? 0, visibility: placement ? 'visible' : 'hidden' }} data-testid="cue-window">
        <CuePanel view={view} onAction={onAction} onSize={onSize} still={still} />
      </div>
      {ui ? (
        <div style={{ position: 'absolute', right: 16, top: 36, display: 'flex', gap: 8, alignItems: 'center', padding: 8, background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 6, font: '500 12px var(--font-body)', zIndex: 10 }}>
          <select value={id} onChange={(e) => setId(e.target.value)} style={{ font: 'inherit', maxWidth: 300 }}>
            {Object.entries(STORIES).map(([k, s]) => (
              <option key={k} value={k}>
                {s.label}
              </option>
            ))}
          </select>
          <button type="button" onClick={() => setTheme((t) => !t)} style={{ font: 'inherit' }}>
            {theme ? 'Dark' : 'Light'}
          </button>
        </div>
      ) : null}
    </div>
  )
}

createRoot(document.getElementById('root') as HTMLElement).render(<Storyboard />)
