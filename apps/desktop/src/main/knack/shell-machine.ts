// The window, the corner column and the menu bar as one machine: the 18 transitions of docs/knack-ux/08-window-states.md (as data: docs/knack-ux/shell-transitions.json)
// as a pure reducer. `reduce(state, event)` returns the next state and the effects; knack-shell.ts performs the effects (Electron, the corner column, the tray) and
// feeds events in. No Electron, no clock, no randomness here.
//
// Invariants (each has a test):
//   - at most one pill and one card exist; a card is replaced only by a higher-priority one (stopped > safety > approval > time > digest > cue)
//   - the main window is restored or opened only by a Dock click or Activate, the menu bar's Open Knack, a click on Review, or a deep link the worker clicked
//   - close never quits, never hides the Dock icon, never stops a run
//   - kill always wins: any state goes to stopped, and only Resume leaves it
//   - a card never takes focus and ignores clicks for its first 600 ms (carried on the effect that draws it)
//   - no card is shown while macOS secure input is on, except stopped and safety; the Ask bar holds every card except those two while it is open

export type WindowState = 'absent' | 'open' | 'minimised'
export type Activity = 'idle' | 'working' | 'voice' | 'error' | 'stopped'
export type PillKind = 'none' | 'working' | 'done' | 'error' | 'voice'
export type CardKind = 'none' | 'stopped' | 'safety' | 'approval' | 'time' | 'digest' | 'cue'
export type DecisionClass = 'approval' | 'safety' | 'time'
export type VoicePhase = 'Listening' | 'Thinking' | 'Speaking'

/** Highest first. */
export const CARD_PRIORITY: readonly Exclude<CardKind, 'none'>[] = ['stopped', 'safety', 'approval', 'time', 'digest', 'cue']
const rank = (k: CardKind): number => (k === 'none' ? 99 : CARD_PRIORITY.indexOf(k))
/** True when `a` may replace `b` on screen (strictly higher priority, or nothing shown). */
export const outranks = (a: CardKind, b: CardKind): boolean => rank(a) < rank(b)

export const TIMING = { minimiseDelayMs: 400, doneMs: 2500, fadeMs: 240, mistapGuardMs: 600, awayMinutes: 30 } as const

export interface ShellState {
  window: WindowState
  focused: boolean
  activity: Activity
  corner: { pill: PillKind; card: CardKind }
  /** Cards that arrived while they could not be shown (secure input, the Ask bar, a better card on screen): the highest is drawn when it can be. */
  held: readonly Exclude<CardKind, 'none'>[]
  /** The setting "Move aside while Knack works". */
  moveAside: boolean
  secureInput: boolean
  askBarOpen: boolean
  /** Things waiting for the worker (the menu-bar count and the Dock badge). */
  needsYou: number
  /** A marker on the menu bar after an error was acknowledged. */
  errorMarker: boolean
}

export const INITIAL_SHELL: ShellState = { window: 'open', focused: true, activity: 'idle', corner: { pill: 'none', card: 'none' }, held: [], moveAside: true, secureInput: false, askBarOpen: false, needsYou: 0, errorMarker: false }

export type ShellEvent =
  | { type: 'run_started'; realScreen: boolean }
  | { type: 'run_progress'; label: string; n?: number; m?: number }
  | { type: 'decision_needed'; class: DecisionClass }
  | { type: 'review_clicked'; item?: string }
  | { type: 'run_done'; needsNothing: boolean }
  | { type: 'run_failed' }
  | { type: 'error_acknowledged' }
  | { type: 'kill' }
  | { type: 'resume' }
  | { type: 'voice_hold'; phase: VoicePhase }
  | { type: 'voice_end' }
  | { type: 'ask_tap' }
  | { type: 'ask_closed' }
  | { type: 'returned_after_30min'; count: number }
  | { type: 'window_close' }
  | { type: 'window_minimise' }
  | { type: 'dock_click_or_activate' }
  | { type: 'menu_open_knack' }
  | { type: 'deep_link' }
  | { type: 'quit'; running: boolean; awayRoutineDueWithin24h?: boolean }
  | { type: 'quit_choice'; choice: 'stop_and_quit' | 'keep_working' }
  // An approval, a cue or a digest card that arrived from the attention layer or the permission broker (not from a run).
  | { type: 'card_arrived'; kind: Exclude<CardKind, 'none' | 'stopped'> }
  | { type: 'card_dismissed' }
  | { type: 'done_timer' }
  | { type: 'secure_input'; on: boolean }
  // The window's real state, so the machine matches what the worker did with it. No effects.
  | { type: 'window_state'; window?: WindowState; focused?: boolean }
  | { type: 'settings'; moveAside: boolean }
  | { type: 'needs_you_count'; n: number }

export type Effect =
  | { type: 'minimizeMainAfter'; ms: number }
  | { type: 'showPill'; label: string }
  | { type: 'pillLabel'; label: string }
  | { type: 'pillCount'; n: number; m: number }
  | { type: 'pillVoice'; label: VoicePhase; end: true }
  | { type: 'pillCheck'; ms: number }
  | { type: 'fade'; ms: number }
  | { type: 'hideCornerWindow' }
  | { type: 'pillError'; holdUntilAcknowledged: true }
  | { type: 'menubar'; state: 'working' | 'workingOff' | 'stopped' | 'idle' | 'count' | 'marker'; count?: number }
  | { type: 'dockBadge'; count: number }
  | { type: 'dockBadgeIfDecision'; count: number }
  | { type: 'cardAbovePill'; kind: Exclude<CardKind, 'none'>; mistapGuardMs: number; takesFocus: false }
  | { type: 'closeCard' }
  | { type: 'stopAll' }
  | { type: 'stoppedCardReplacesPill' }
  | { type: 'closeStoppedCard' }
  | { type: 'inWindowBannerIfOpen' }
  | { type: 'bannerOff' }
  | { type: 'openOrRestoreMain'; screen: 'needs-you'; item?: string }
  | { type: 'openMain'; screen: 'home'; bounds: 'last' }
  | { type: 'restoreMain' }
  | { type: 'focusMain' }
  | { type: 'hideMain'; keepRendererAlive: true }
  | { type: 'minimizeMain' }
  | { type: 'openAskBar' }
  | { type: 'holdCards'; except: readonly ['stopped', 'safety'] }
  | { type: 'releaseCards' }
  | { type: 'digestCardOnce' }
  | { type: 'quitSheet'; routineLine: boolean }
  | { type: 'quit' }
  | { type: 'stopAndQuit' }
  | { type: 'noWindowRestore' }

/** The words of docs/knack-ux/shell-transitions.json for an effect, so the table-driven test can compare. */
export function tokenOf(e: Effect): string {
  switch (e.type) {
    case 'minimizeMainAfter':
      return `minimizeMainAfter${e.ms}ms`
    case 'showPill':
      return `showPill(${e.label})`
    case 'pillLabel':
      return 'pillLabel(<=5 words)'
    case 'pillCount':
      return 'pillCount(n of m when known)'
    case 'pillVoice':
      return `pill(${e.label}, End)`
    case 'pillCheck':
      return `pillCheck(${e.ms}ms)`
    case 'fade':
      return `fade(${e.ms}ms)`
    case 'pillError':
      return 'pillError(holdUntilAcknowledged)'
    case 'menubar':
      return e.state === 'marker' ? 'menubarMarker' : `menubar(${e.state})`
    case 'dockBadge':
      return 'dockBadge(count)'
    case 'dockBadgeIfDecision':
      return 'dockBadgeIfDecision'
    case 'cardAbovePill':
      return 'cardAbovePill(by priority)'
    case 'stoppedCardReplacesPill':
      return 'stoppedCardReplacesPill'
    case 'inWindowBannerIfOpen':
      return 'inWindowBannerIfOpen'
    case 'openOrRestoreMain':
      return 'openOrRestoreMain(NeedsYou, item)'
    case 'hideMain':
      return 'hideMain(keepRendererAlive)'
    case 'holdCards':
      return 'holdCards(except stopped, safety)'
    case 'digestCardOnce':
      return 'digestCardOnce'
    case 'quitSheet':
      return 'quitSheet(Stop and quit | Keep working)'
    default:
      return e.type
  }
}

/** Effects that bring the main window up or forward. Only a few events may produce them. */
export const WINDOW_RESTORING: ReadonlySet<Effect['type']> = new Set(['openOrRestoreMain', 'openMain', 'restoreMain', 'focusMain'])

const words = (s: string): string => s.trim().split(/\s+/).slice(0, 5).join(' ')
const result = (state: ShellState, effects: Effect[] = []): { state: ShellState; effects: Effect[] } => ({ state, effects })

const mayShow = (s: ShellState, kind: Exclude<CardKind, 'none'>): boolean => {
  if (kind === 'stopped' || kind === 'safety') return true
  return !s.secureInput && !s.askBarOpen
}
const draw = (kind: Exclude<CardKind, 'none'>): Effect => ({ type: 'cardAbovePill', kind, mistapGuardMs: TIMING.mistapGuardMs, takesFocus: false })
const best = (held: readonly Exclude<CardKind, 'none'>[]): Exclude<CardKind, 'none'> | null => CARD_PRIORITY.find((k) => held.includes(k)) ?? null

/** Puts a card in front of the worker if it may be shown and outranks what is up; otherwise holds it. The returned effect list is empty when nothing is drawn. */
function offer(s: ShellState, kind: Exclude<CardKind, 'none'>): { state: ShellState; effects: Effect[] } {
  if (s.corner.card === kind) return { state: s, effects: [] } // already on screen: one card, not two
  if (mayShow(s, kind) && outranks(kind, s.corner.card)) {
    const replaced = s.corner.card !== 'none' && s.corner.card !== kind ? [s.corner.card] : []
    return { state: { ...s, corner: { ...s.corner, card: kind }, held: [...s.held.filter((k) => k !== kind), ...replaced.filter((k) => k !== 'stopped')] }, effects: [draw(kind)] }
  }
  return { state: { ...s, held: s.held.includes(kind) ? s.held : [...s.held, kind] }, effects: [] }
}

/** Draws the best held card if there is room for one (after the Ask bar closes, secure input ends or a card goes). */
function release(s: ShellState): { state: ShellState; effects: Effect[] } {
  const next = best(s.held.filter((k) => mayShow(s, k)))
  if (next && outranks(next, s.corner.card)) return { state: { ...s, corner: { ...s.corner, card: next }, held: s.held.filter((k) => k !== next) }, effects: [draw(next)] }
  return { state: s, effects: [] }
}

const countEffects = (n: number): Effect[] => [{ type: 'menubar', state: 'count', count: n }, { type: 'dockBadge', count: n }]

export function reduce(s: ShellState, ev: ShellEvent): { state: ShellState; effects: Effect[] } {
  // Kill wins: while stopped, runs and voice do nothing; only resume (and the things that do not run anything) are heard.
  if (s.activity === 'stopped' && ['run_started', 'run_progress', 'run_done', 'run_failed', 'voice_hold', 'decision_needed'].includes(ev.type)) {
    if (ev.type === 'decision_needed' && ev.class === 'safety') return offer({ ...s, needsYou: s.needsYou + 1 }, 'safety') // a safety card replaces nothing above the stopped card: offer() holds it
    return result(s)
  }
  switch (ev.type) {
    // ---- 1, 2, 3
    case 'run_started': {
      const next: ShellState = { ...s, activity: 'working', corner: { ...s.corner, pill: 'working' } }
      const effects: Effect[] = []
      if (ev.realScreen && s.window === 'open' && s.focused && s.moveAside) effects.push({ type: 'minimizeMainAfter', ms: TIMING.minimiseDelayMs })
      effects.push({ type: 'showPill', label: 'Starting' }, { type: 'menubar', state: 'working' })
      return result(next, effects)
    }
    // ---- 4
    case 'run_progress': {
      if (s.activity !== 'working') return result(s)
      const effects: Effect[] = [{ type: 'pillLabel', label: words(ev.label) }]
      if (ev.n !== undefined && ev.m !== undefined && ev.m > 0) effects.push({ type: 'pillCount', n: ev.n, m: ev.m })
      return result(s, effects)
    }
    // ---- 5
    case 'decision_needed': {
      const counted: ShellState = { ...s, needsYou: s.needsYou + 1 }
      const o = offer(counted, ev.class)
      return result(o.state, [...o.effects, ...countEffects(o.state.needsYou), { type: 'noWindowRestore' }])
    }
    case 'card_arrived': {
      const o = offer(s, ev.kind)
      return result(o.state, o.effects)
    }
    case 'card_dismissed': {
      if (s.corner.card === 'none' || s.corner.card === 'stopped') return result(s)
      const cleared: ShellState = { ...s, corner: { ...s.corner, card: 'none' } }
      const r = release(cleared)
      return result(r.state, [{ type: 'closeCard' }, ...r.effects])
    }
    // ---- 6
    case 'review_clicked': {
      const cleared: ShellState = { ...s, window: 'open', focused: true, corner: { ...s.corner, card: s.corner.card === 'stopped' ? 'stopped' : 'none' } }
      return result(cleared, [{ type: 'openOrRestoreMain', screen: 'needs-you', ...(ev.item ? { item: ev.item } : {}) }, { type: 'closeCard' }])
    }
    // ---- 7
    case 'run_done': {
      if (s.activity !== 'working' && s.activity !== 'voice') return result(s)
      const next: ShellState = { ...s, activity: 'idle', corner: { ...s.corner, pill: ev.needsNothing ? 'done' : 'none' } }
      const effects: Effect[] = ev.needsNothing ? [{ type: 'pillCheck', ms: TIMING.doneMs }, { type: 'fade', ms: TIMING.fadeMs }, { type: 'hideCornerWindow' }] : []
      return result(next, [...effects, { type: 'noWindowRestore' }, { type: 'menubar', state: 'workingOff' }])
    }
    case 'done_timer':
      return s.corner.pill === 'done' ? result({ ...s, corner: { ...s.corner, pill: 'none' } }) : result(s)
    // ---- 8
    case 'run_failed': {
      if (s.activity !== 'working' && s.activity !== 'voice') return result(s)
      return result({ ...s, activity: 'error', corner: { ...s.corner, pill: 'error' }, errorMarker: false }, [{ type: 'pillError', holdUntilAcknowledged: true }, { type: 'menubar', state: 'marker' }, { type: 'dockBadgeIfDecision', count: s.needsYou }, { type: 'noWindowRestore' }])
    }
    case 'error_acknowledged': {
      if (s.activity !== 'error') return result(s)
      return result({ ...s, activity: 'idle', corner: { ...s.corner, pill: 'none' }, errorMarker: true }, [{ type: 'hideCornerWindow' }, { type: 'menubar', state: 'marker' }])
    }
    // ---- 9
    case 'kill': {
      const heldSafety = s.held.filter((k) => k === 'safety')
      return result(
        { ...s, activity: 'stopped', corner: { pill: 'none', card: 'stopped' }, held: heldSafety },
        [{ type: 'stopAll' }, { type: 'stoppedCardReplacesPill' }, { type: 'inWindowBannerIfOpen' }, { type: 'menubar', state: 'stopped' }, { type: 'noWindowRestore' }],
      )
    }
    // ---- 10
    case 'resume': {
      if (s.activity !== 'stopped') return result(s)
      const cleared: ShellState = { ...s, activity: 'idle', corner: { pill: 'none', card: 'none' } }
      const r = release(cleared)
      return result(r.state, [{ type: 'closeStoppedCard' }, { type: 'bannerOff' }, { type: 'menubar', state: 'idle' }, ...r.effects])
    }
    // ---- 11
    case 'voice_hold':
      return result({ ...s, activity: s.activity === 'working' ? 'working' : 'voice', corner: { ...s.corner, pill: s.activity === 'working' ? 'working' : 'voice' } }, [{ type: 'pillVoice', label: ev.phase, end: true }])
    case 'voice_end':
      return s.activity === 'voice' ? result({ ...s, activity: 'idle', corner: { ...s.corner, pill: 'none' } }, [{ type: 'hideCornerWindow' }]) : result(s)
    // ---- 12
    case 'ask_tap':
      return result({ ...s, askBarOpen: true }, [{ type: 'openAskBar' }, { type: 'holdCards', except: ['stopped', 'safety'] }])
    case 'ask_closed': {
      const r = release({ ...s, askBarOpen: false })
      return result(r.state, [{ type: 'releaseCards' }, ...r.effects])
    }
    case 'secure_input': {
      const r = release({ ...s, secureInput: ev.on })
      return result(r.state, r.effects)
    }
    // ---- 13
    case 'returned_after_30min': {
      if (ev.count <= 0) return result(s)
      const counted: ShellState = { ...s, needsYou: ev.count }
      const o = offer(counted, 'digest')
      // The digest card is drawn once, when it can be (else it is held and drawn at the next break); the count is on the menu bar and the Dock either way.
      return result(o.state, [...(o.effects.length > 0 ? [{ type: 'digestCardOnce' } as Effect, ...o.effects] : []), ...countEffects(ev.count)])
    }
    // ---- 14, 15
    case 'window_close':
      return result({ ...s, window: 'absent', focused: false }, [{ type: 'hideMain', keepRendererAlive: true }])
    case 'window_minimise':
      return result({ ...s, window: 'minimised', focused: false }, [{ type: 'minimizeMain' }])
    // ---- 16 (and the menu's Open Knack, and a deep link the worker clicked: the same three outcomes)
    case 'dock_click_or_activate':
    case 'menu_open_knack':
    case 'deep_link': {
      const from = s.window
      const next: ShellState = { ...s, window: 'open', focused: true }
      if (from === 'absent') return result(next, [{ type: 'openMain', screen: 'home', bounds: 'last' }])
      if (from === 'minimised') return result(next, [{ type: 'restoreMain' }])
      return result(next, s.focused ? [] : [{ type: 'focusMain' }])
    }
    // ---- 17, 18
    case 'quit': {
      if (!ev.running) return result(s, [{ type: 'quit' }])
      return result(s, [{ type: 'quitSheet', routineLine: ev.awayRoutineDueWithin24h === true }])
    }
    case 'quit_choice':
      return ev.choice === 'stop_and_quit' ? result(s, [{ type: 'stopAndQuit' }]) : result(s)
    // ---- bookkeeping, no effects
    case 'window_state':
      return result({ ...s, window: ev.window ?? s.window, focused: ev.focused ?? s.focused })
    case 'settings':
      return result({ ...s, moveAside: ev.moveAside })
    case 'needs_you_count':
      return result({ ...s, needsYou: ev.n }, countEffects(ev.n))
  }
}
