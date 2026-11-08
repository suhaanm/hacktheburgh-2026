// The Hey Knack controller: keeps the on-device listener running exactly when it may (guards.ts), and turns a `heard` into a Live conversation
// through the SAME manager entry the talk key uses, with the first-wake consent cards and the gated `do_it_for_me` click. Pure assembly of
// injected ports (tests drive it with fakes); wake/electron.ts builds the real ones.
//
// What it never does: start the listener while any guard says dormant; give the listener's audio to any model (the helper only says `heard`);
// click anything itself (the click machine only emits effects, and the card's Allow counts only as a real mouse click).
import type { VoiceLock } from '../attention/lock'
import type { DoItAnswer, DoItRequest, TaskAnswer } from '../live/ports'
import { parseTypedTask, type ConsentCard, type ConsentChoice, type QuestionCard, type TaskClient, type TaskRow } from './tasks'
import { INITIAL, reduce, type ClickEffect, type ClickEvent, type ClickState, type ToolAnswer } from './click-machine'
import { dormancy, type Dormancy, type WakeInputs } from './guards'
import type { HelperStatus } from './helper'
import type { RungReading } from './rung'
import { consentOutcome, consentStep, type CardChoice, type WakeSettingsStore } from './settings'
import { BLOCKED_LINE, CARDS, EVERYTHING_CARD, FIRST_WAKE_OPENING, FIRST_WAKE_OPENING_SETUP, STARTED_CARD, TYPED_LINES, doneCard, failedCard, showInsteadCard, typedFailureLine, taskConsentCard, taskQuestionCard, taskResultCard, clickFailureCard, LISTENING_LINE, REFUSAL_LINE, dormantLine, infoCardWith, type InfoCard } from './texts'

export interface CardSpec {
  id: string
  title: string
  body: string
  buttons: ReadonlyArray<{ id: string; label: string }>
  expireMs: number
}
export interface CardAnswer {
  buttonId: string
  /** 'mouse' only for a real, trusted mouse click on the button (not a key, not a synthetic event). */
  via: 'mouse' | 'other'
}
export interface CardPort {
  ask(spec: CardSpec): Promise<CardAnswer | null>
  close(id: string): void
}

export interface HelperPort {
  start(): void
  stop(): void
  status(): HelperStatus
  unblock(): void
}

export interface LivePort {
  /** What would stop a conversation opening now, leaving consent out (the cards ask for that). Null: nothing. */
  blocker(): string | null
  startFromWake(): boolean
  status(): { phase: string; trigger: 'key' | 'wake' | null; refused: string | null; /** Why the last conversation could not hear or answer (a closed code), or null. */ problem?: string | null }
  subscribe(cb: () => void): () => void
}

export interface LiveSettingsPort {
  get(): { liveEnabled: boolean; liveConsentVersion: number; liveFrames: boolean }
  patch(raw: unknown, opts?: { trusted?: boolean }): unknown
}

export interface DesktopRunPort {
  /** Asks the agent service to click the centre of the box once (full pipeline and real-actuator guards). Never throws. */
  run(req: { box: [number, number, number, number]; cardId: string }): Promise<{ ok: boolean; reason?: string }>
  stop(): void
}

export interface WakeStatus {
  /** The worker's switch. */
  switchOn: boolean
  /** The helper is running and armed. */
  listening: boolean
  dormant: Dormancy | null
  helper: HelperStatus
  /** A Live conversation that began with the words is open. */
  session: boolean
  click: ClickState['k']
  /** The one plain line for the menu bar and Settings. */
  line: string
  /** The macOS pane that fixes a blocked listener (a button next to the line in Settings), or null. */
  fix: 'microphone' | 'speech' | 'dictation' | null
  /** The worker has had their first conversation (the Try it step is done). */
  welcomed: boolean
}

export interface WakeControllerDeps {
  settings: WakeSettingsStore
  liveSettings: LiveSettingsPort
  live: LivePort
  helper: HelperPort
  inputs: () => Omit<WakeInputs, 'switchedOn' | 'liveSessionActive' | 'firstRunHold'>
  /** First-run set-up is on screen (the context hub's flag). Until the permissions step calls `arm()`, the listener waits. Absent: never waits. */
  firstRun?: () => boolean
  cards: CardPort
  lock: VoiceLock
  rung: () => RungReading
  desktop: DesktopRunPort
  chime?: () => void
  /** The button on an information card: Knack's Settings, or the macOS microphone pane. */
  openSettings?: (where: 'knack' | 'microphone' | 'screen' | 'speech' | 'accessibility' | 'dictation' | 'sound') => void
  /** The macOS microphone status (read only, never asks). 'not-determined' makes the microphone card say Allow instead of System Settings. Absent: always System Settings. */
  micStatus?: () => string
  /** How long a listener blocked for a permission waits before it tries again by itself (so a grant made in System Settings is picked up). Default 30 s. */
  retryBlockedMs?: number
  say?: (line: 'show_instead' | 'done' | 'did_not_work' | 'stopped' | 'started') => void
  /** The task service (loopback). Absent: `start_task` answers that it is unavailable. */
  tasks?: TaskClient
  /** Reads a result line out in the open conversation (data, not an instruction). False when no conversation is open: a card then shows it. */
  readOut?: (text: string) => boolean
  /** Waits (tests move time by hand). */
  sleep?: (ms: number) => Promise<void>
  /** How often a started task is looked at, and for how long. */
  taskPollMs?: number
  taskWatchMs?: number
  now?: () => number
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
  setInterval?: (fn: () => void, ms: number) => unknown
  clearInterval?: (h: unknown) => void
  log?: (scope: string, ...args: unknown[]) => void
  /** How long the listener stays off after a conversation ends, so the microphone is free of the last one. */
  restartDelayMs?: number
  pollMs?: number
  cardMs?: number
}

export interface WakeController {
  start(): void
  dispose(): void
  status(): WakeStatus
  subscribe(cb: (s: WakeStatus) => void): () => void
  /** Settings switch (a trusted write from the Settings screen or the menu). */
  setListen(on: boolean): void
  /** The kill switch changed (Stop everything engaged or cleared). */
  setKilled(killed: boolean): void
  /** Re-reads every guard now (screen lock, call, agent state changed). */
  refresh(): void
  /** A capability that cannot work right now answers with a plain card and a button, never silence (the talk key, pointing without Screen Recording). Rate-limited per reason. */
  explainRefusal(reason: string): void
  /** The set-up step that turns Hey Knack on: the listener may start (and macOS asks for the microphone, then Speech Recognition, in that order). */
  arm(): void
  /** The opening turn for the very first conversation (trusted, fixed words), or null once the worker has been welcomed. */
  openingText(): string | null
  /** The helper said `heard`. Exposed for the supervisor and for tests. */
  onHeard(): Promise<void>
  /** The Ask bar's Return with no conversation open: the worker's own line becomes a task (source typed). ok: the bar closes; otherwise one plain sentence and the text stays. */
  submitTyped(text: string): Promise<{ ok: boolean; line?: string }>
  /** The Live tool `start_task`: hands the worker's request to the task service, shows the consent card, never starts anything itself. */
  startTask(text: string): Promise<TaskAnswer>
  /** The wake session's `do_it_for_me` (the Live tool host calls it). */
  doIt(req: DoItRequest): Promise<DoItAnswer>
}

/** Blocked causes the worker fixes in System Settings: the listener is armed again by itself after the fix. */
const RETRYABLE: ReadonlySet<string> = new Set(['mic_denied', 'mic_restricted', 'speech_denied', 'speech_restricted'])

export function createWakeController(d: WakeControllerDeps): WakeController {
  const now = d.now ?? Date.now
  const setT = d.setTimer ?? ((fn, ms) => setTimeout(fn, ms))
  const clearT = d.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>))
  const setI = d.setInterval ?? ((fn, ms) => setInterval(fn, ms))
  const clearI = d.clearInterval ?? ((h) => clearInterval(h as ReturnType<typeof setInterval>))
  const log = d.log ?? (() => undefined)
  const restartDelay = d.restartDelayMs ?? 1500
  const cardMs = d.cardMs ?? 20_000

  let machine: ClickState = INITIAL
  let killed = false
  let started = false
  let armed = false
  let cooldownUntil = 0 // the listener stays off until this time (after a conversation)
  let waking = false // between the words and the conversation opening
  let wakeSession = false
  let lastRefusal: string | null = null
  let pollHandle: unknown = null
  let offLive: (() => void) | null = null
  let cardSeq = 0
  let pendingAnswer: ((a: ToolAnswer) => void) | null = null
  let currentCard: { id: string; box: [number, number, number, number] } | null = null
  let pendingBox: [number, number, number, number] | null = null
  let restartTimer: unknown = null
  const lastExplained = new Map<string, number>()
  const sleep = d.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)))
  const watching = new Set<string>()
  // Tasks the worker typed: they get no spoken line, their words appear on cards instead.
  const typedIds = new Set<string>()
  let taskCardId: string | null = null // the task consent or question card on screen, closed by Stop everything
  let blockedShown: string | null = null // the helper's blocked cause already explained on a card (cleared when the listener works again)
  let blockedAt: number | null = null // when the helper was first seen blocked for a permission (it tries again after a while)
  let lastProblem: string | null = null // the conversation problem already explained on a card (cleared when the next conversation opens)
  const listeners = new Set<(s: WakeStatus) => void>()

  const liveOpen = (): boolean => {
    const p = d.live.status().phase
    return p !== 'idle' && p !== 'off'
  }

  const input = (): WakeInputs => ({ ...d.inputs(), switchedOn: d.settings.get().wakeListen, firstRunHold: !armed && d.firstRun?.() === true, killed: killed || d.inputs().killed, liveSessionActive: liveOpen() || waking })

  const status = (): WakeStatus => {
    const dorm = dormancy(input())
    const h = d.helper.status()
    const listening = dorm === null && h.state === 'listening'
    let line = LISTENING_LINE
    if (h.state === 'blocked' && h.code && dorm !== 'switched_off') line = BLOCKED_LINE[h.code]
    else if (dorm) line = dormantLine(dorm)
    else if (h.state !== 'listening' && lastRefusal) line = lastRefusal
    else if (h.state === 'starting' || h.state === 'backoff') line = 'Starting Hey Knack.'
    const fix = h.state === 'blocked' && dorm !== 'switched_off' ? (h.code === 'mic_denied' || h.code === 'mic_restricted' ? 'microphone' : h.code === 'speech_denied' || h.code === 'speech_restricted' ? 'speech' : h.code === 'on_device_unavailable' || h.code === 'locale_unsupported' ? 'dictation' : null) : null
    return { switchOn: d.settings.get().wakeListen, listening, dormant: dorm, helper: h, session: wakeSession, click: machine.k, line, fix, welcomed: d.settings.get().welcomed }
  }
  let lastKey = ''
  const publish = (): void => {
    const s = status()
    const key = JSON.stringify([s.switchOn, s.listening, s.dormant, s.helper, s.session, s.click, s.line, s.fix, s.welcomed])
    if (key === lastKey) return
    lastKey = key
    for (const l of listeners) {
      try {
        l(s)
      } catch {
        /* a listener never breaks the controller */
      }
    }
  }

  // ---- the click machine: events in, effects out
  const dispatch = (e: ClickEvent): void => {
    const r = reduce(machine, e, ++cardSeq)
    machine = r.state
    for (const eff of r.effects) perform(eff)
    publish()
  }

  function perform(eff: ClickEffect): void {
    switch (eff.t) {
      case 'answer': {
        const p = pendingAnswer
        pendingAnswer = null
        p?.(eff.answer)
        break
      }
      case 'say':
        d.say?.(eff.line)
        break
      case 'show_card': {
        const id = `click-${eff.cardId}`
        currentCard = { id, box: pendingBox ?? [0, 0, 0, 0] }
        const text = CARDS.click
        void d.cards.ask({ id, title: text.title, body: text.body, buttons: text.buttons, expireMs: cardMs }).then((a) => {
          if (currentCard?.id !== id) return // already closed (kill, session end)
          if (!a) return dispatch({ t: 'card_choice', choice: 'cancel', via: 'timer' })
          const allow = a.buttonId === 'allow'
          dispatch({ t: 'card_choice', choice: allow ? 'allow' : 'cancel', via: a.via === 'mouse' ? 'mouse' : 'key' })
          // An Allow that was not a real mouse click is refused by the machine; the card is answered, so the request ends here as a Cancel.
          if (allow && a.via !== 'mouse') dispatch({ t: 'card_choice', choice: 'cancel', via: 'timer' })
        })
        break
      }
      case 'close_card':
        if (currentCard) {
          const id = currentCard.id
          if (machine.k !== 'running') currentCard = null
          d.cards.close(id)
        }
        break
      case 'request_run': {
        const c = currentCard
        currentCard = null
        if (!c) break
        void d.desktop.run({ box: c.box, cardId: c.id }).then(
          (r) => {
            dispatch({ t: 'run_result', ok: r.ok })
            if (!r.ok && machine.k !== 'killed') explain(clickFailureCard(r.reason)) // a click that could not run says why, once, and Knack shows instead
          },
          () => dispatch({ t: 'run_result', ok: false }),
        )
        break
      }
      case 'stop_run':
        d.desktop.stop()
        break
      case 'ignored':
        log('wake', `ignored: ${eff.why}`)
        break
    }
  }

  // ---- the listener: running exactly when no guard says dormant
  function evaluate(): void {
    if (!started) return
    const dorm = dormancy(input())
    // A listener blocked for a permission never retries by itself, so the worker who then switched it on in System Settings would have to toggle Hey Knack off and on. Instead: when the
    // microphone is now allowed, or after a while for the others (speech recognition has no read-only status), it is armed again. Nothing here asks macOS: a refused permission does not prompt.
    const hb = d.helper.status()
    if (hb.state === 'blocked' && hb.code && RETRYABLE.has(hb.code) && dorm !== 'switched_off') {
      blockedAt ??= now()
      const micNowOn = (hb.code === 'mic_denied' || hb.code === 'mic_restricted') && d.micStatus?.() === 'granted'
      if (micNowOn || now() - blockedAt >= (d.retryBlockedMs ?? 30_000)) {
        blockedAt = null
        d.helper.unblock()
      }
    } else blockedAt = null
    const h = d.helper.status()
    const holdOff = now() < cooldownUntil
    if (dorm === null && !holdOff) {
      if (h.state === 'stopped') d.helper.start()
      if (d.helper.status().state === 'listening' && machine.k === 'idle') dispatch({ t: 'listen_on' })
    } else {
      if (h.state !== 'stopped' && h.state !== 'blocked') d.helper.stop()
      if (machine.k === 'listening') dispatch({ t: 'listen_off' })
    }
    // The listener blocked for want of a permission or on-device speech: say so on a card once (a status line alone is easy to miss), with the button.
    const hs = d.helper.status()
    if (hs.state === 'blocked' && hs.code && dorm !== 'switched_off') {
      const cause = `blocked_${hs.code}`
      if (blockedShown !== cause && infoCardWith(cause)) {
        blockedShown = cause
        explain(cause)
      }
    } else if (hs.state === 'listening') blockedShown = null
    publish()
  }

  const schedule = (ms: number): void => {
    if (restartTimer !== null) clearT(restartTimer)
    restartTimer = setT(() => {
      restartTimer = null
      evaluate()
    }, ms)
  }

  // ---- the words were heard
  async function onHeard(): Promise<void> {
    if (!started || waking || dormancy(input()) !== null || machine.k !== 'listening') return
    waking = true
    lastRefusal = null
    dispatch({ t: 'wake' })
    d.helper.stop() // the microphone is released before the conversation opens its own
    try {
      // The words were heard, so the worker always gets an answer: when a conversation cannot open at all (no live models, the service not answering, the
      // microphone not allowed) a card says why in plain words, before any consent is asked for something that could not happen anyway.
      const blocker = d.live.blocker()
      if (blocker !== null && blocker !== 'busy') {
        lastRefusal = REFUSAL_LINE[blocker] ?? null
        if (blocker === 'mic_permission') lastProblem = blocker // explained here: the status change that follows does not show the same card again
        explain(blocker)
        return end(`blocked_${blocker}`)
      }
      if (!(await consent())) return end('declined')
      if (!d.lock.acquire('asked', 120_000, undefined, 'wake')) return end('lock_held')
      d.chime?.()
      if (!d.live.startFromWake()) {
        const why = d.live.status().refused ?? ''
        lastRefusal = REFUSAL_LINE[why] ?? 'Knack could not start talking.'
        d.lock.release('asked', 'wake')
        if (why === 'mic_permission') lastProblem = why
        explain(why)
        return end('refused')
      }
      wakeSession = true
      waking = false
      if (!d.settings.get().welcomed) d.settings.patch({ welcomed: true }, { trusted: true })
    } catch {
      end('error')
    } finally {
      publish()
    }
  }

  /** An information card for a refusal (never silence). Fire and forget: the listener comes back after its pause either way. */
  function explain(reason: string): void {
    const card: InfoCard | null = infoCardWith(reason, { micStatus: d.micStatus?.() })
    if (!card) return
    const id = `info-${++cardSeq}`
    void d.cards.ask({ id, title: card.title, body: card.body, buttons: card.buttons, expireMs: 20_000 }).then((a) => {
      // A button counts only as a real mouse click (the card window never answers otherwise).
      if (a && a.via === 'mouse' && a.buttonId === card.buttons[0].id && card.action) d.openSettings?.(card.action === 'settings' ? 'knack' : card.action)
    })
  }

  /** A conversation (the talk key's or Hey Knack's) that could not hear or answer says why, once, on a card: the microphone not allowed, a private app in front, the voice service not answering. Never silence. */
  function explainProblem(): void {
    const st = d.live.status()
    const p = st.problem ?? (st.refused === 'mic_permission' ? 'mic_permission' : null)
    if (!p) {
      lastProblem = null
      return
    }
    if (p === lastProblem) return
    lastProblem = p
    lastRefusal = REFUSAL_LINE[p] ?? lastRefusal
    explain(p)
  }

  function end(why: string): void {
    log('wake', `no conversation: ${why}`)
    waking = false
    wakeSession = false
    d.lock.release('asked', 'wake')
    if (machine.k !== 'killed') dispatch({ t: 'session_ended' })
    cooldownUntil = now() + restartDelay
    schedule(restartDelay)
    publish()
  }

  /** The first-wake cards, one at a time. True when the conversation may open. */
  async function consent(): Promise<boolean> {
    for (let i = 0; i < 2; i++) {
      const step = consentStep(d.settings.get(), d.liveSettings.get(), now())
      if (step.step === 'go') return true
      if (step.step === 'refused') return false
      const text = CARDS[step.card]
      const a = await d.cards.ask({ id: `consent-${step.card}`, title: text.title, body: text.body, buttons: text.buttons, expireMs: 30_000 })
      // Only a real mouse click on a button is an answer. A key, a timer or a closed card is no answer: nothing is remembered, nothing opens.
      if (!a || a.via !== 'mouse' || !['yes', 'not_now', 'never'].includes(a.buttonId)) return false
      const out = consentOutcome(step.card, a.buttonId as CardChoice, d.liveSettings.get().liveFrames, new Date(now()))
      d.settings.patch(out.wake, { trusted: true })
      d.liveSettings.patch(out.live, { trusted: true })
      if (a.buttonId !== 'yes' && step.card === 'voice') return false
    }
    return consentStep(d.settings.get(), d.liveSettings.get(), now()).step === 'go'
  }

  // ---- the model's do_it_for_me
  // ---- "Hey Knack, do X": the task service, the consent card, and what Knack says when it is done
  const failureCard = (reason: string): string => (reason === 'too_many_tasks' ? 'too_many_tasks' : reason === 'kill_switch' ? 'killed' : 'task_unavailable')

  /** A started task is looked at every couple of seconds until it finishes: Done. on success, a plain line if it failed, and an answer read out or shown. */
  function watch(id: string): void {
    if (!d.tasks || watching.has(id)) return
    watching.add(id)
    const pollMs = d.taskPollMs ?? 2000
    const until = now() + (d.taskWatchMs ?? 30 * 60_000)
    const tick = async (): Promise<void> => {
      if (!started || now() > until) return void watching.delete(id)
      const row = await d.tasks?.get(id).catch(() => null)
      if (row && (row.state === 'done' || row.state === 'failed' || row.state === 'stopped')) {
        watching.delete(id)
        finished(row)
        return
      }
      await sleep(pollMs)
      void tick()
    }
    void tick()
  }

  /** What is said for an answered question: the full answer when the service gave it (cut to what is worth saying aloud), else the one-line result. */
  const speakable = (row: TaskRow): string | null => (row.answer ?? row.result)?.slice(0, 300) ?? null

  function finished(row: TaskRow): void {
    const typed = typedIds.has(row.task_id)
    if (row.state === 'stopped') return // the worker stopped it (or declined): nothing to say
    if (row.state === 'failed') {
      if (typed) void d.cards.ask({ id: `failed-${row.task_id}`, ...failedCard(row.reason), expireMs: 20_000 })
      else d.say?.('did_not_work')
      return
    }
    if (row.route === 'answer' && (row.answer || row.result)) {
      const said = speakable(row) ?? row.result ?? ''
      const spoken = !typed && d.readOut?.(said) === true
      if (!spoken) void d.cards.ask({ id: `result-${row.task_id}`, ...taskResultCard(said), expireMs: 30_000 })
      return
    }
    if (typed) void d.cards.ask({ id: `done-${row.task_id}`, ...doneCard(row.result), expireMs: 20_000 })
    else d.say?.('done')
  }

  /** The consent card for a task, answered only by a real mouse click. Not now and a timeout leave the task waiting (it is still in Needs you). */
  async function confirm(id: string, nc: ConsentCard | null): Promise<void> {
    if (!d.tasks || !nc) return
    const card = taskConsentCard(nc)
    taskCardId = `task-${id}`
    let a = await d.cards.ask({ id: taskCardId, title: card.title, body: card.body, buttons: card.buttons, expireMs: 120_000 })
    if (!a || a.via !== 'mouse') return void (taskCardId = null)
    let choice: ConsentChoice | null = a.buttonId === 'decline' ? 'decline' : a.buttonId === 'allow' ? 'allow' : null
    if (a.buttonId === 'more' && nc.buttons.more.some((m) => m.id === 'everything')) {
      taskCardId = `task-${id}-more`
      a = await d.cards.ask({ id: taskCardId, title: EVERYTHING_CARD.title, body: EVERYTHING_CARD.body, buttons: EVERYTHING_CARD.buttons, expireMs: 120_000 })
      choice = a && a.via === 'mouse' && a.buttonId === 'everything' ? 'everything' : null
    }
    taskCardId = null
    if (choice === null) return
    const r = await d.tasks.consent(id, choice)
    if (!r.ok) return explain(failureCard(r.reason))
    if (choice === 'decline') return
    if (typedIds.has(id)) void d.cards.ask({ id: `started-${id}`, ...STARTED_CARD, expireMs: 8000 })
    else d.say?.('started')
    watch(id)
  }

  async function askQuestion(id: string, q: QuestionCard | null): Promise<void> {
    if (!d.tasks || !q) return
    const card = taskQuestionCard(q)
    taskCardId = `task-${id}-q`
    const a = await d.cards.ask({ id: taskCardId, title: card.title, body: card.body, buttons: card.buttons, expireMs: 120_000 })
    taskCardId = null
    if (!a || a.via !== 'mouse') return
    const r = await d.tasks.answer(id, a.buttonId)
    if (!r.ok) return explain(failureCard(r.reason))
    if (r.row?.needs_consent) return void confirm(id, r.row.needs_consent)
    if (r.row && (r.row.state === 'running' || r.row.state === 'planning')) watch(id)
  }

  async function submitTyped(raw: string): Promise<{ ok: boolean; line?: string }> {
    if (!d.tasks) return { ok: false, line: TYPED_LINES.no_service }
    const text = parseTypedTask(raw)
    if (text === null) return { ok: false }
    if (machine.k === 'killed') return { ok: false, line: TYPED_LINES.kill_switch }
    const r = await d.tasks.create(text, 'typed')
    if (!r.ok) return { ok: false, line: typedFailureLine(r.reason) }
    const c = r.created
    typedIds.add(c.task_id)
    if (c.question) {
      void askQuestion(c.task_id, c.question)
      return { ok: true }
    }
    if (c.needs_consent) {
      void confirm(c.task_id, c.needs_consent)
      return { ok: true }
    }
    // No card: a request the service would not take at all comes back failed at once, with its own plain reason: that stays under the input with the text.
    const row = await d.tasks.get(c.task_id).catch(() => null)
    if (row?.state === 'failed') return { ok: false, line: row.reason ?? TYPED_LINES.refused }
    if (c.route === 'desktop') {
      void d.cards.ask({ id: `desktop-${c.task_id}`, ...showInsteadCard(c.summary), expireMs: 30_000 })
      return { ok: true }
    }
    if (c.route === 'unclear') return { ok: false, line: TYPED_LINES.unclear }
    watch(c.task_id) // an answer or a finished job appears on a card
    return { ok: true }
  }

  async function startTask(text: string): Promise<TaskAnswer> {
    if (!d.tasks) return { ok: false, reason: 'unavailable' }
    if (machine.k === 'killed') return { ok: false, reason: 'kill_switch' }
    const r = await d.tasks.create(text)
    if (!r.ok) {
      const why = r.reason === 'too_many_tasks' || r.reason === 'kill_switch' || r.reason === 'refused' ? r.reason : 'unavailable'
      explain(failureCard(r.reason))
      return { ok: false, reason: why }
    }
    const c = r.created
    if (c.question) {
      void askQuestion(c.task_id, c.question)
      return { ok: true, started: false, waiting_consent: false, route: c.route, asked: true }
    }
    if (c.needs_consent) {
      void confirm(c.task_id, c.needs_consent)
      return { ok: true, started: false, waiting_consent: true, route: c.route }
    }
    if (c.route === 'desktop') return { ok: true, started: false, waiting_consent: false, route: 'desktop', desktop_click_possible: d.rung().cleared }
    if (c.route === 'answer') {
      // A question answered inline: wait a few seconds for the one result line, which the model then says.
      for (let i = 0; i < 20; i++) {
        const row = await d.tasks.get(c.task_id).catch(() => null)
        if (row && (row.state === 'done' || row.state === 'failed' || row.state === 'stopped')) return { ok: true, started: false, waiting_consent: false, route: 'answer', result: row.state === 'done' ? speakable(row) : null }
        await sleep(1000)
      }
      watch(c.task_id) // still working: it is read out or shown when it finishes
      return { ok: true, started: false, waiting_consent: false, route: 'answer', result: null }
    }
    return { ok: true, started: false, waiting_consent: false, route: c.route }
  }

  async function doIt(req: DoItRequest): Promise<DoItAnswer> {
    if (machine.k === 'card_shown' || machine.k === 'running') return { ok: false, reason: 'busy' }
    const rung = d.rung()
    pendingBox = req.box
    const answer = new Promise<ToolAnswer>((resolve) => {
      pendingAnswer = resolve
    })
    dispatch({ t: 'tool_call', rungCleared: rung.cleared, targetFound: req.box !== null })
    return answer
  }

  return {
    start() {
      if (started) return
      started = true
      offLive = d.live.subscribe(() => {
        const open = liveOpen()
        if (wakeSession && !open && d.live.status().trigger === null) {
          // The wake conversation ended (goodbye, quiet, cap, Stop, kill).
          wakeSession = false
          d.lock.release('asked', 'wake')
          if (d.live.status().refused === 'mic_permission') lastRefusal = REFUSAL_LINE.mic_permission
          dispatch({ t: 'session_ended' })
          cooldownUntil = now() + restartDelay
          schedule(restartDelay)
        } else if (open && wakeSession) d.lock.extend('asked', 120_000, 'wake')
        explainProblem()
        evaluate()
      })
      pollHandle = setI(() => evaluate(), d.pollMs ?? 3000)
      evaluate()
    },
    dispose() {
      started = false
      if (pollHandle !== null) clearI(pollHandle)
      pollHandle = null
      if (restartTimer !== null) clearT(restartTimer)
      restartTimer = null
      offLive?.()
      offLive = null
      d.helper.stop()
      if (currentCard) d.cards.close(currentCard.id)
      if (taskCardId) d.cards.close(taskCardId)
      watching.clear()
      listeners.clear()
    },
    status,
    subscribe(cb) {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    setListen(on) {
      d.settings.patch({ wakeListen: on }, { trusted: true })
      if (on) d.helper.unblock()
      evaluate()
    },
    setKilled(k) {
      killed = k
      if (k && taskCardId) d.cards.close(taskCardId)
      dispatch({ t: k ? 'kill' : 'resume' })
      evaluate()
    },
    refresh: evaluate,
    startTask,
    submitTyped,
    arm() {
      armed = true
      d.helper.unblock()
      evaluate()
    },
    // The very first conversation gets the welcome: the set-up variant while set-up is still open (it has no sidebar), the ordinary one after it.
    openingText: () => (d.settings.get().welcomed ? null : d.firstRun?.() === true ? FIRST_WAKE_OPENING_SETUP : FIRST_WAKE_OPENING),
    explainRefusal(reason) {
      const t = now()
      const last = lastExplained.get(reason) ?? -Infinity
      if (t - last < (reason === 'screen_recording' ? 10 * 60_000 : 20_000)) return
      lastExplained.set(reason, t)
      // The talk key before the worker has agreed to talk: the same two cards as the first wake, then a line saying it is on.
      if (reason === 'not_enabled' || reason === 'no_consent') {
        void consent().then((ok) => ok && explain('ready'), () => undefined)
        return
      }
      if (reason === 'mic_permission') lastProblem = reason // the key press explained it already
      explain(reason)
    },
    onHeard,
    doIt,
  }
}
