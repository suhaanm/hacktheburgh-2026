// The Cue controller: asks the engine for the current decision about every 1.5 s, runs it through the state machine (machine.ts) and carries
// out what the machine asks for through ports (overlay, panel, engine, voice, speaker). Everything it touches is injected, so the whole
// of Cue runs under a fake clock in a test and under fixtures in the storyboard. It never opens the microphone, never speaks unless the guards
// say so, never captures the screen and never logs a frame, a box or any text.
import type { NormBox } from '../../shared/protocol'
import type { DomTarget } from '../dom-ground/protocol'
import { mayWhisper, type CueProactivity, type Policy } from './guards'
import type { CueCardAction, CueView } from './ipc'
import { INITIAL_MACHINE, nextDeadline, reduce, type Effect, type MachineEvent, type MachineState } from './machine'
import type { CueEnginePort } from './source'
import { CUE_TOKENS } from './tokens'
import { cueKey } from './machine'
import { parseCueDecision, sameCue, type CueDecision, type CueTargetSource } from './types'
import { OTHER_OPTION_ID, type CueSpeaker, type CueVoice, type LiveCuePort } from './voice'

export interface OverlayPort {
  show(annotations: import('../../shared/protocol').Annotation[]): void
  clear(ids?: string[]): void
}

export interface PanelPort {
  /** Show this view (null hides the panel). `anchor` is what it keeps clear of; `keep` leaves it where it is (the card collapsing). */
  set(view: CueView, o: { anchor: NormBox | null; kind: 'chip' | 'card'; keep: boolean }): void
  /** The global keys while a cue is up: Alt+1..n answer, Alt+0 "something else", Alt+Escape dismiss. */
  keys(o: { answers: number; dismiss: boolean }): void
  dispose(): void
}

/** Asked about a ring whose screen changed: still there, gone, or found somewhere else (a box on the 0..1000 grid, [y0, x0, y1, x1]). */
export interface CueGrounder {
  /**
   * One question: is the ring's element where the ring is? `target` is the step's zone (null: nothing to look for, answer 'gone'); `key` is
   * episode plus step (the same on every poll that keeps the cue up). 'same': leave it; 'gone': hide it; { box }: it moved, draw it there.
   */
  recheck(t: { key: string; stepId: string | null; box: NormBox; source: CueTargetSource; target: DomTarget | null }): Promise<'same' | 'gone' | { box: [number, number, number, number] }>
  /**
   * Keep following the ring's element for as long as the cue is up (scrolling, a re-layout): `onBox` when it moved or came back, `onGone` when
   * it cannot be found or was scrolled away. Returns the stop. Optional: without it only `recheck` runs, after a screen change.
   */
  follow?(t: { key: string; target: DomTarget; box: NormBox }, cb: { onBox(box: [number, number, number, number]): void; onGone(): void }): () => void
}

export interface CueSignals {
  typingNow(): boolean
  workerUsedVoice(): boolean
  // The worker is not at the screen (locked, idle, on a call, sharing the screen): sent to the engine as away=1. Optional.
  away?(): boolean
  // Seconds since the last keyboard or pointer input (to a tenth), or null when unreadable: sent as quiet_s. The engine holds with reason
  // `flow` when typing is on or quiet_s is under 2 s; it is not a hold time. Optional (the engine then derives it from its own events).
  quietS?(): number | null
}

/**
 * The one-voice rule (ATTENTION): a cue, a question or an offer and a toast never coexist. Cue asks before it draws something NEW; a cue that is
 * already up growing a tier is a continuation and is not asked about again. All of it is optional: without it Cue behaves as before.
 */
export interface AttentionPort {
  /**
   * About to draw this new cue. Resolves { show: true } to draw (the one-voice lock is then held for the cue's life), { show: false } to veto.
   * `onPreempt` is called if something more important (safety, a decision) takes the voice: Cue must hide at once. A veto is not a worker
   * reaction: Cue sends nothing to the engine for it. If this rejects, Cue stays quiet (fail closed).
   */
  admit(d: CueDecision, onPreempt: () => void): Promise<{ show: boolean; itemId: string | null }>
  /** The cue is gone (hidden, dismissed, answered, progressed, expired): give the voice back. */
  release(): void
  /** Same moments as the engine feedback, for the attention router's own learning: ids and a number of seconds only. */
  feedback?(itemId: string, event: 'shown' | 'followed' | 'dismissed' | 'ignored', seconds: number): void
}

export interface CueSettingsView {
  proactivity: CueProactivity
  voice: boolean
}

export interface CueControllerDeps {
  engine: CueEnginePort
  overlay: OverlayPort
  panel: PanelPort
  policy: () => Policy
  settings: () => CueSettingsView
  signals?: Partial<CueSignals>
  voice?: CueVoice
  speaker?: CueSpeaker
  grounder?: CueGrounder
  attention?: AttentionPort
  // "Something else" was chosen: open the conversation (the worker's choice; Live, opt-in). Not called by default.
  onConverse?: () => void
  // UNDERSTUDY_VOICE=1 in this build.
  buildVoiceOn?: boolean
  chord?: string
  now?: () => number
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
  log?: (scope: string, ...args: unknown[]) => void
}

export interface CueController {
  start(): void
  stop(): void
  /** One poll now (the worker asked: a hotkey, or yes to an offer). */
  poll(o?: { asked?: boolean }): Promise<void>
  action(a: CueCardAction): void
  /** The worker got past this step (null: some step). Optional extra to the engine's own progress reasons. */
  progress(stepId: string | null): void
  /** The capture watcher saw the screen change (0..1). A ring whose target may have moved is checked, and hidden if it did. */
  screenChanged(score: number): void
  /** Settings, kill switch or flag changed: take down whatever is up if Cue may no longer speak. */
  refresh(): void
  visible(): { kind: CueDecision['kind']; seq: number } | null
  livePort(): LiveCuePort
  dispose(): void
}

export function createCueController(deps: CueControllerDeps): CueController {
  const now = deps.now ?? Date.now
  const setT = deps.setTimer ?? ((fn, ms) => setTimeout(fn, ms))
  const clearT = deps.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>))
  const log = deps.log ?? (() => undefined)
  // (spread would let an explicit `undefined` from the caller replace a default)
  const sig: CueSignals = { typingNow: deps.signals?.typingNow ?? (() => false), workerUsedVoice: deps.signals?.workerUsedVoice ?? (() => false), away: deps.signals?.away, quietS: deps.signals?.quietS }
  let state: MachineState = INITIAL_MACHINE
  let deadline: unknown = null
  let pollTimer: unknown = null
  let polling = false
  let askedWhilePolling = false
  let started = false
  let keysSig = ''
  const answerListeners = new Set<(id: string) => void>()
  // Pack steps seen so far (id -> label): the closed list the voice tools may name.
  const known = new Map<string, string>()
  let localEpisode = 0
  // The one-voice lock is held for the cue on screen (and the router's id for it).
  let held: { itemId: string | null } | null = null
  const ATTENTION_EVENT: Record<string, 'shown' | 'followed' | 'dismissed' | 'ignored'> = { shown: 'shown', accepted: 'followed', answered: 'followed', dismissed: 'dismissed', know_this: 'dismissed', abandoned: 'ignored' }

  // A step is the same step on every poll that keeps its cue up: episode plus step id.
  const stepKey = (d: CueDecision): string => `${d.episode_id}/${d.step?.id ?? ''}`

  // Following the ring on the page: one follower per cue that has a ring and a zone, stopped when the cue goes or is replaced.
  let following: { seq: number; stop: () => void } | null = null
  const syncFollower = (): void => {
    const v = state.visible
    const grounder = deps.grounder
    const target = v?.decision.step?.target ?? null
    const want = v && !v.pending && v.plan.ring && target && grounder?.follow ? v : null
    if (following && (!want || following.seq !== want.seq)) {
      following.stop()
      following = null
    }
    if (!want || !target || !grounder?.follow || following) return
    const seq = want.seq
    const stop = grounder.follow(
      { key: stepKey(want.decision), target, box: want.plan.ring?.box as NormBox },
      {
        onBox: (box) => {
          if (state.visible?.seq === seq) dispatch({ type: 'retarget', box })
        },
        onGone: () => {
          if (state.visible?.seq === seq) dispatch({ type: 'stale' })
        },
      },
    )
    following = { seq, stop }
  }

  const wantsVoice = (asked: boolean): boolean => deps.settings().voice && (deps.buildVoiceOn ?? false) && (sig.workerUsedVoice() || asked)

  const syncKeys = (): void => {
    const v = state.visible
    const answers = v && !v.pending ? (v.plan.question?.options.length ?? 0) : 0
    const dismiss = v !== null && v.decision.kind !== 'confirm'
    const next = `${answers}/${dismiss}`
    if (next === keysSig) return
    keysSig = next
    deps.panel.keys({ answers, dismiss })
  }

  const schedule = (): void => {
    if (deadline !== null) clearT(deadline)
    deadline = null
    const d = nextDeadline(state)
    if (d !== null) deadline = setT(() => dispatch({ type: 'tick' }), Math.max(0, d - now()) + 5)
  }

  function run(effects: Effect[]): void {
    for (const e of effects) {
      switch (e.type) {
        case 'overlay':
          if (e.clear.length) deps.overlay.clear(e.clear)
          if (e.show.length) deps.overlay.show(e.show)
          break
        case 'panel':
          deps.panel.set(e.view, { anchor: e.anchor, kind: e.kind, keep: e.keep })
          break
        case 'keys':
          break // derived from the state after the whole batch (syncKeys)
        case 'feedback':
          void deps.engine.feedback(e.event).catch(() => undefined)
          // (a "Show me" is a request for more help, not the cue being followed: the router is not told it was)
          if (held?.itemId && e.event.scope === 'cue' && e.event.how !== 'show_me' && ATTENTION_EVENT[e.event.event]) deps.attention?.feedback?.(held.itemId, ATTENTION_EVENT[e.event.event], e.event.seconds)
          if (e.event.event === 'answered' && e.event.option_id) for (const cb of answerListeners) cb(e.event.option_id)
          break
        case 'speak': {
          const v = state.visible
          const text = v?.plan.whisper?.text
          const ok = mayWhisper({ cueVoice: deps.settings().voice, buildVoiceOn: deps.buildVoiceOn ?? false, workerUsedVoice: sig.workerUsedVoice(), asked: e.asked, typingNow: sig.typingNow(), cardUp: v?.plan.question != null || v?.plan.offer != null })
          if (ok && deps.speaker && text) {
            deps.speaker.registerLine?.(e.lineId, text)
            void Promise.resolve(deps.speaker.say(e.lineId)).catch(() => undefined)
          }
          break
        }
        case 'listen': {
          // Only with the worker's voice switched on and a voice provided: Cue itself never opens the microphone.
          const seq = state.visible?.seq
          if (!deps.voice || !wantsVoice(false)) break
          void deps.voice
            .listenOnce(e.options, { timeoutMs: CUE_TOKENS.timing.listenMs })
            .then((id) => {
              if (id && state.visible?.seq === seq && state.visible?.plan.question) dispatch({ type: 'answer', id })
            })
            .catch(() => undefined)
          break
        }
        case 'converse':
          deps.onConverse?.()
          break
        case 'reground': {
          const v = state.visible
          if (!deps.grounder || !v) break
          const seq = v.seq
          void deps.grounder
            .recheck({ key: stepKey(v.decision), stepId: v.decision.step?.id ?? null, box: e.box, source: v.decision.target?.source ?? 'none', target: v.decision.step?.target ?? null })
            .then((r) => {
              if (typeof r === 'object' && state.visible?.seq === seq) dispatch({ type: 'retarget', box: r.box })
            })
            .catch(() => undefined)
          break
        }
        case 'poll':
          void poll({ asked: e.asked })
          break
      }
    }
  }

  function dispatch(ev: MachineEvent): void {
    const r = reduce(state, ev, { now: now(), policy: deps.policy(), chord: deps.chord })
    state = r.state
    run(r.effects)
    syncKeys()
    schedule()
    // Nothing of Cue's is on the screen any more: the voice goes back to whoever is next.
    if (held && !state.visible) {
      held = null
      deps.attention?.release()
    }
    syncFollower()
  }

  function remember(d: CueDecision): void {
    if (d.step) known.set(d.step.id, d.step.label)
    for (const o of d.options ?? []) known.set(o.id, o.label)
  }

  async function poll(o: { asked?: boolean } = {}): Promise<void> {
    if (polling) {
      if (o.asked) askedWhilePolling = true
      return
    }
    const p = deps.policy()
    // Off or killed: nothing is asked of the engine; whatever is up comes down.
    if (!p.enabled || p.killed) {
      if (state.visible) dispatch({ type: 'stop', how: p.killed ? 'killed' : 'off' })
      return
    }
    polling = true
    try {
      const asked = o.asked === true || askedWhilePolling
      askedWhilePolling = false
      const raw = await deps.engine.next({ asked: asked || undefined, voiceOk: wantsVoice(asked), proactivity: deps.settings().proactivity, denied: p.suppressed !== null, away: sig.away?.() || undefined, quietS: sig.quietS?.() ?? undefined, typing: sig.typingNow() || undefined })
      if (raw === null) return // the engine did not answer: what is up stays until its own limits
      const d = parseCueDecision(raw)
      remember(d)
      const v = state.visible
      const starting = (d.kind === 'cue' || d.kind === 'ask' || d.kind === 'offer') && !(v && sameCue(v.decision, d)) && !state.ended.includes(cueKey(d))
      if (deps.attention && starting) {
        // The router decides whether now is a moment for a new voice; a cue already up growing a tier is not asked again.
        const verdict = await deps.attention.admit(d, () => dispatch({ type: 'stop', how: 'off' })).catch(() => ({ show: false, itemId: null }))
        if (!verdict.show) return // a veto is not the worker's reaction: nothing is drawn and nothing is reported
        const seq = state.seq
        held = { itemId: verdict.itemId }
        dispatch({ type: 'decision', decision: d })
        // Cue's own rules (caps, quiet, level 4) may still have refused it: then the voice is given straight back.
        if (state.seq === seq && held) {
          held = null
          deps.attention.release()
        }
        return
      }
      dispatch({ type: 'decision', decision: d })
    } catch (err) {
      log('cue', `poll failed: ${err instanceof Error ? err.name : 'error'}`)
    } finally {
      polling = false
    }
  }

  const inject = (d: CueDecision): boolean => {
    remember(d)
    dispatch({ type: 'decision', decision: d })
    return state.visible !== null && state.visible.decision.kind === d.kind
  }
  const episodeId = (): string => state.episode?.id ?? `live-local-${++localEpisode}`

  const port: LiveCuePort = {
    candidates: () => [...known.entries()].slice(-6).map(([id, label]) => ({ id, label })),
    showStep(stepId) {
      const label = known.get(stepId)
      if (!label) return { ok: false, chip: null }
      const d = parseCueDecision({ kind: 'cue', episode_id: episodeId(), tier: 2, step: { id: stepId, label }, target: { box_2d: null, source: 'none', confidence: 0 }, say: { chip: `Next: ${label}` }, trigger: 'asked', why: { level: 2, reasons: ['asked'] } })
      const ok = d.kind === 'cue' && inject(d)
      return { ok, chip: ok ? d.say.chip : null }
    },
    askChoice(optionIds) {
      const options = optionIds.filter((id, i) => known.has(id) && optionIds.indexOf(id) === i).slice(0, CUE_TOKENS.card.maxOptions).map((id) => ({ id, label: known.get(id) as string }))
      if (options.length < 2) return false
      const d = parseCueDecision({ kind: 'ask', episode_id: episodeId(), options: [...options, { id: OTHER_OPTION_ID, label: 'Something else' }], question: { type: 'close_call', text: 'Which of these is next?' }, trigger: 'asked', why: { level: 2, reasons: ['asked'] } })
      return d.kind === 'ask' && inject(d)
    },
    onAnswer(cb) {
      answerListeners.add(cb)
      return () => void answerListeners.delete(cb)
    },
  }

  return {
    start() {
      if (started) return
      started = true
      pollTimer = (deps.setTimer ?? ((fn: () => void, ms: number) => setInterval(fn, ms)))(() => void poll(), CUE_TOKENS.timing.pollMs)
    },
    stop() {
      started = false
      if (pollTimer !== null) (deps.clearTimer ?? ((h: unknown) => clearInterval(h as ReturnType<typeof setInterval>)))(pollTimer)
      pollTimer = null
      if (state.visible) dispatch({ type: 'stop', how: 'off' })
    },
    poll,
    action(a) {
      switch (a.type) {
        case 'answer':
          return dispatch({ type: 'answer', id: a.id })
        case 'other':
          return dispatch({ type: 'answer', id: OTHER_OPTION_ID })
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
    progress: (stepId) => dispatch({ type: 'progress', stepId }),
    screenChanged(score) {
      const v = state.visible
      if (!v || !v.plan.ring || v.hiddenAt !== null || score < CUE_TOKENS.screenChangeScore) return
      const ring = v.plan.ring
      if (!deps.grounder) {
        dispatch({ type: 'stale' })
        return
      }
      const seq = v.seq
      void deps.grounder
        .recheck({ key: stepKey(v.decision), stepId: v.decision.step?.id ?? null, box: ring.box, source: v.decision.target?.source ?? 'none', target: v.decision.step?.target ?? null })
        .then((r) => {
          if (state.visible?.seq !== seq || r === 'same') return
          dispatch({ type: 'stale' })
          if (typeof r === 'object') dispatch({ type: 'retarget', box: r.box })
        })
        .catch(() => dispatch({ type: 'stale' }))
    },
    refresh() {
      const p = deps.policy()
      if (state.visible && (!p.enabled || p.killed || p.suppressed || (p.quietUntil !== null && now() < p.quietUntil) || (p.pausedUntil !== null && now() < p.pausedUntil))) {
        dispatch({ type: 'stop', how: p.killed ? 'killed' : p.quietUntil !== null || p.pausedUntil !== null ? 'quiet' : 'off' })
      }
    },
    visible: () => (state.visible ? { kind: state.visible.decision.kind, seq: state.visible.seq } : null),
    livePort: () => port,
    dispose() {
      this.stop()
      if (deadline !== null) clearT(deadline)
      deadline = null
      answerListeners.clear()
      following?.stop()
      following = null
      deps.panel.dispose()
    },
  }
}
