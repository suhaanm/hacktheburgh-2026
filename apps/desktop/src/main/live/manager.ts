// The voice manager: the hold-to-talk key in, at most one conversation at a time, the start gates, the caps, the breaker.
//
//   bus 'talk' press     -> start a conversation (or, if a Cue question is waiting for a spoken answer, a one-answer listening turn)
//   bus 'talk' release   -> the worker's turn is over; the conversation ends after a quiet grace
//   bus 'session:ended'  -> the shell's Stop or the kill switch: end everything now
//
// Nothing here opens a microphone or a socket unless: the flags are on (flags.ts), the worker opted in (settings.ts), the kill switch is
// off, no agent is acting, the spending caps have room, the breaker is closed, and macOS has ALREADY granted microphone access (this code
// never asks for it). When any of that fails, the press does nothing audible and `status().refused` says why in a closed code; the Cue
// question card keeps working because it never depended on voice.
import type { Bus } from '../bus'
import { dayKey } from '../awareness/usage'
import { LiveSession, type EndReason, type FrameProvider, type SessionConfig, type SessionMode, type SessionSummary } from './session'
import { CircuitBreaker, SessionMeter, createUsageLog, pricesFromEnv, type LivePrices, type UsageLog } from './meter'
import { GateMonitor, createGateReader, type GateReader, type GateSources, type Timers as GateTimers } from './gates'
import { LIVE_SYSTEM_INSTRUCTION, TRANSCRIBE_ONLY_INSTRUCTION, WAKE_SYSTEM_INSTRUCTION } from './prompt'
import { liveFlagOn, liveModelId, transcribeModelId, type Env } from './flags'
import { frameConsent, voiceConsent, type LiveSettingsStore } from './settings'
import { createToolHost } from './tool-host'
import { buildToolDeclarations } from './tools'
import { FALLBACK_PACKET, packetUpdate } from '../wake/context-packet'
import type { FunctionDeclaration } from './wire'
import { realTimers, type Timers } from './clock'
import type { SocketFactory } from './connection'
import type { LiveLedgerPort } from './ledger'
import type { AudioBridge, DoItAnswer, DoItRequest, GroundPort, LiveCuePort, RingPort } from './ports'
import type { ModelCheck, TokenMinter } from './token'
import type { TurnMode } from './wire'

// Context engineering: the provider keeps at most about this much running context for a conversation (system instruction, tool declarations,
// frames and turns); past the trigger it slides the window down to the target. A conversation is at most five minutes, so this is a ceiling.
export const CONTEXT_TRIGGER_TOKENS = 8000
export const CONTEXT_TARGET_TOKENS = 4000

export type Refusal =
  | 'flag_off'
  | 'not_enabled'
  | 'no_consent'
  | 'paused'
  | 'killed'
  | 'agent_acting'
  | 'day_cap'
  | 'breaker_open'
  | 'no_model'
  | 'model_unusable'
  | 'no_key'
  | 'mock_mode'
  | 'mic_permission'
  | 'busy'

export type ManagerPhase = 'off' | 'idle' | 'connecting' | 'listening' | 'thinking' | 'speaking' | 'waiting'

export interface LiveStatus {
  flagOn: boolean
  enabled: boolean
  phase: ManagerPhase
  elapsedMs: number
  maxMs: number
  mode: SessionMode | null
  // What started the open conversation: the talk key, or the words "Hey Knack" (hands-free). Null when none is open.
  trigger: 'key' | 'wake' | null
  todayUsd: number
  dailyUsd: number
  sessionsToday: number
  breakerOpen: boolean
  usedVoice: boolean
  refused: Refusal | null
  lastEnd: { reason: EndReason; at: number; usd: number; mode: SessionMode } | null
  // The most recent conversation's numbers (never content): ttfa per answered turn, tool names and outcomes, tokens by modality.
  lastSummary: Omit<SessionSummary, 'transcript'> | null
}

export interface ManagerDeps {
  env?: Env
  settings: LiveSettingsStore
  bus: Pick<Bus, 'on'>
  tokens: TokenMinter
  modelCheck?: () => Promise<ModelCheck>
  gateSources: GateSources
  gateTimers?: GateTimers
  ledger: LiveLedgerPort
  audio: AudioBridge
  frames?: FrameProvider | null
  cue: LiveCuePort
  ground?: GroundPort | null
  ring: RingPort
  // Wake sessions only: what `do_it_for_me` asks. Absent: the tool answers "not available" and the model shows instead.
  doIt?: (req: DoItRequest) => Promise<DoItAnswer>
  // The code-built context packet for a conversation (enums, ids and counts only; wake/context-packet.ts). It goes into the system instruction at
  // start and, changed lines only, as an update every ten seconds. Absent or throwing: the session starts with the fixed fallback text.
  context?: (o: { tools: FunctionDeclaration[]; trigger: 'key' | 'wake' }) => string
  usage?: UsageLog
  breaker?: CircuitBreaker
  prices?: LivePrices
  micStatus: () => 'granted' | 'denied' | 'not-determined' | 'restricted' | 'unknown'
  agentActing: () => boolean
  killed: () => boolean
  appKind?: () => string | undefined
  turnMode?: TurnMode
  socketFactory?: SocketFactory
  url?: string
  timers?: Timers
  now?: () => number
  log?: (scope: string, ...args: unknown[]) => void
}

export interface LiveManager {
  start(): void
  dispose(): void
  status(): LiveStatus
  subscribe(cb: (s: LiveStatus) => void): () => void
  /** Ends whatever is running now (the kill switch, Stop, quit). */
  stopAll(reason?: EndReason): void
  workerUsedVoice(): boolean
  /** Cue's one-answer turn: waits for a talk press within `timeoutMs`, listens while it is held, resolves with the words heard or null. */
  listen(timeoutMs: number): Promise<string | null>
  /** The worker answered the question card: tell the running conversation which step they meant. */
  noteAnswer(id: string): void
  hasSession(): boolean
  voiceAllowed(): boolean
  /** The words "Hey Knack" were heard: open a hands-free conversation through the same gates as the key. False (with `status().refused` set) when it may not start. */
  startFromWake(): boolean
}

export function createLiveManager(d: ManagerDeps): LiveManager {
  const env = d.env ?? process.env
  const now = d.now ?? Date.now
  const timers = d.timers ?? realTimers
  const log = d.log ?? (() => undefined)
  const usage = d.usage ?? createUsageLog(null)
  const breaker = d.breaker ?? new CircuitBreaker({ now })
  const reader: GateReader = createGateReader(d.gateSources)
  const listeners = new Set<(s: LiveStatus) => void>()

  let session: LiveSession | null = null
  let sessionMode: SessionMode | null = null
  let sessionTrigger: 'key' | 'wake' | null = null
  let lastPacket: string | null = null
  let ctxTicks = 0
  let toolHostDispose: (() => void) | null = null
  let offAnswer: (() => void) | null = null
  let usedVoice = false
  let refused: Refusal | null = null
  let lastEnd: LiveStatus['lastEnd'] = null
  let lastSummary: LiveStatus['lastSummary'] = null
  let modelState: ModelCheck | null = null
  let waiter: { resolve: (t: string | null) => void; timer: unknown; started: boolean } | null = null
  let tickHandle: unknown = null
  let started = false
  let offBus: Array<() => void> = []

  const phase = (): ManagerPhase => {
    if (!liveFlagOn(env)) return 'off'
    if (!session || session.isEnded) return 'idle'
    return session.phase === 'ended' ? 'idle' : session.phase
  }

  const status = (): LiveStatus => {
    const s = d.settings.get()
    return {
      flagOn: liveFlagOn(env),
      enabled: voiceConsent(s),
      phase: phase(),
      elapsedMs: session && !session.isEnded ? session.elapsedMs : 0,
      maxMs: s.liveMaxMs,
      mode: session && !session.isEnded ? sessionMode : null,
      trigger: session && !session.isEnded ? sessionTrigger : null,
      todayUsd: Math.round(usage.todayUsd(now()) * 1e6) / 1e6,
      dailyUsd: s.liveDailyUsd,
      sessionsToday: usage.todaySessions(now()),
      breakerOpen: breaker.isOpen(),
      usedVoice,
      refused,
      lastEnd,
      lastSummary,
    }
  }
  const emit = (): void => {
    const snap = status()
    for (const l of listeners) {
      try {
        l(snap)
      } catch {
        /* a listener never breaks a session */
      }
    }
  }

  // ---- may a conversation start now? (all code, first failing reason)
  function startRefusal(): Refusal | null {
    const s = d.settings.get()
    if (!liveFlagOn(env)) return 'flag_off'
    if (!s.liveEnabled) return 'not_enabled'
    if (!voiceConsent(s)) return 'no_consent'
    if (s.livePausedUntilMs > now()) return 'paused'
    if (d.killed()) return 'killed'
    if (d.agentActing()) return 'agent_acting'
    if (usage.todayUsd(now()) >= s.liveDailyUsd) return 'day_cap'
    if (breaker.isOpen()) return 'breaker_open'
    if (!liveModelId(env)) return 'no_model'
    // Mock mode (the offline demo and the tests) never opens a real voice session.
    if (env.UNDERSTUDY_MOCK === '1' || env.ALONGSIDE_MOCK === '1') return 'mock_mode'
    if (!(env.GEMINI_API_KEY ?? '').trim()) return 'no_key'
    if (modelState && !modelState.ok && modelState.reason !== 'unreachable') return modelState.reason === 'no_key' ? 'no_key' : 'model_unusable'
    // Never ask: reading the status cannot raise the macOS prompt. The owner grants it in System Settings.
    if (d.micStatus() !== 'granted') return 'mic_permission'
    return null
  }

  function configFor(mode: SessionMode, wake = false, context = ''): SessionConfig {
    const s = d.settings.get()
    const live = liveModelId(env) as string
    const tm = transcribeModelId(env)
    const base = { turnMode: d.turnMode ?? 'vad', silenceTailMs: 700, dayBaseUsd: usage.todayUsd(now()), dailyUsd: s.liveDailyUsd, compressTriggerTokens: CONTEXT_TRIGGER_TOKENS, compressTargetTokens: CONTEXT_TARGET_TOKENS }
    if (mode === 'transcribe') {
      return { ...base, mode, model: tm ?? live, textOnlyModel: tm !== null, voiceName: s.liveVoiceName, systemInstruction: TRANSCRIBE_ONLY_INSTRUCTION, idleMs: 15_000, graceMs: 3000, maxMs: 25_000, sessionUsd: Math.min(0.05, s.liveSessionUsd), framesEnabled: false, frameIntervalMs: 60_000, transcriptWaitMs: 3000 }
    }
    if (wake) {
      // Hands-free: server-side turn detection, the microphone stays open, a quiet half minute ends it (the key's 60 s is for a held key).
      return { ...base, turnMode: 'vad', mode, wake: true, model: live, voiceName: s.liveVoiceName, systemInstruction: context ? `${WAKE_SYSTEM_INSTRUCTION}\n\n${context}` : WAKE_SYSTEM_INSTRUCTION, idleMs: Math.min(s.liveIdleMs, 30_000), graceMs: s.liveGraceMs, maxMs: s.liveMaxMs, sessionUsd: s.liveSessionUsd, framesEnabled: frameConsent(s), frameIntervalMs: s.liveFrameIntervalMs, transcriptWaitMs: 3000 }
    }
    return { ...base, mode, model: live, voiceName: s.liveVoiceName, systemInstruction: context ? `${LIVE_SYSTEM_INSTRUCTION}\n\n${context}` : LIVE_SYSTEM_INSTRUCTION, idleMs: s.liveIdleMs, graceMs: s.liveGraceMs, maxMs: s.liveMaxMs, sessionUsd: s.liveSessionUsd, framesEnabled: frameConsent(s), frameIntervalMs: s.liveFrameIntervalMs, transcriptWaitMs: 3000 }
  }

  function open(mode: SessionMode, onSummary?: (s: SessionSummary) => void, wake = false): boolean {
    refused = startRefusal()
    if (refused) {
      log('live', `not started: ${refused}`)
      emit()
      onSummary?.({ reason: 'blocked', mode, durationMs: 0, usd: 0, audioInSeconds: 0, audioOutSeconds: 0, frames: 0, turns: 0, ttfaMs: [], ttfrMs: [], transcript: null, tools: [], tokens: { in: {}, out: {} }, costParts: { byTimeUsd: 0, byTokensUsd: 0 }, frameBatches: 0 })
      return false
    }
    const meter = new SessionMeter(d.prices ?? pricesFromEnv(env))
    const host = createToolHost({ cue: d.cue, ground: d.ground ?? null, ring: d.ring, appKind: d.appKind, ...(wake && d.doIt ? { wake: { doIt: d.doIt } } : {}) })
    const gates = new GateMonitor(reader, d.gateTimers, now)
    // The context packet (trusted: code wrote every token). A builder that throws or is missing gives the fixed fallback, never an unstarted session.
    let context = ''
    if (mode === 'converse') {
      const trigger = wake ? 'wake' : 'key'
      try {
        context = d.context ? d.context({ tools: buildToolDeclarations(host.candidates(), { wake, doIt: typeof host.doItForMe === 'function' }), trigger }) : ''
      } catch {
        context = FALLBACK_PACKET
      }
      lastPacket = context || null
    }
    const s = new LiveSession({
      config: configFor(mode, wake, context),
      tokens: d.tokens,
      socketFactory: d.socketFactory,
      url: d.url,
      gates,
      ledger: d.ledger,
      meter,
      audio: d.audio,
      tools: host,
      frames: d.frames ?? null,
      agentActing: d.agentActing,
      killed: d.killed,
      timers: d.timers,
      now,
      log: (...a) => log('live', ...a),
    })
    session = s
    sessionMode = mode
    sessionTrigger = wake ? 'wake' : 'key'
    toolHostDispose = host.dispose
    offAnswer = mode === 'converse' ? d.cue.onAnswer((id) => s.noteAnswer(id)) : null
    s.onPhase(() => emit())
    s.onNotice((n) => {
      if (n.kind === 'mic' && n.reason === 'permission') refused = 'mic_permission'
      emit()
    })
    s.onEnded((summary) => {
      if (session === s) {
        session = null
        sessionMode = null
        sessionTrigger = null
      }
      offAnswer?.()
      offAnswer = null
      toolHostDispose?.()
      toolHostDispose = null
      if (!session && tickHandle !== null) {
        timers.clearInterval(tickHandle)
        tickHandle = null
      }
      lastEnd = { reason: summary.reason, at: now(), usd: summary.usd, mode: summary.mode }
      const { transcript: _heard, ...numbers } = summary
      void _heard
      lastSummary = numbers
      usage.record({
        t: new Date(now()).toISOString(),
        day: dayKey(now()),
        mode: summary.mode,
        seconds_in: summary.audioInSeconds,
        seconds_out: summary.audioOutSeconds,
        frames: summary.frames,
        turns: summary.turns,
        usd: summary.usd,
        ended: summary.reason,
        price_source: meter.priceSource(),
        model: configFor(summary.mode).model,
      })
      // Only a connection that could not be made or kept counts against the breaker.
      if (summary.reason === 'error' || summary.reason === 'connection_lost') breaker.failure()
      else if (summary.turns > 0 || summary.ttfaMs.length > 0) breaker.success()
      onSummary?.(summary)
      emit()
    })
    // The HUD timer: one status push a second, only while a conversation is open.
    if (tickHandle === null) {
      tickHandle = timers.setInterval(() => {
        if (session && !session.isEnded) {
          emit()
          if (sessionMode === 'converse' && d.context && ++ctxTicks % 10 === 0) pushContext()
        }
      }, 1000)
    }
    emit()
    void s.start()
    return true
  }

  // Changed lines of the packet, as one short update into the open conversation. Never throws; a failed build says nothing.
  function pushContext(): void {
    const s = session
    if (!s || s.isEnded || !d.context || lastPacket === null || lastPacket === FALLBACK_PACKET) return
    try {
      const next = d.context({ tools: [], trigger: sessionTrigger ?? 'key' })
      // The tool lines are not part of an update, so a packet built with no tools differs only in lines that can really have changed.
      const update = packetUpdate(lastPacket, next)
      if (update) {
        s.injectText(update)
        lastPacket = next
      }
    } catch {
      /* no update this time */
    }
  }

  // ---- the talk key
  function onTalk(e: { phase: 'press' | 'release' }): void {
    if (!liveFlagOn(env)) return
    if (e.phase === 'press') {
      if (waiter && !waiter.started && (!session || session.isEnded)) {
        waiter.started = true
        usedVoice = true
        const w = waiter
        open('transcribe', (summary) => {
          timers.clearTimeout(w.timer)
          if (waiter === w) waiter = null
          w.resolve(summary.transcript)
        })
        return
      }
      if (session && !session.isEnded) {
        usedVoice = true
        session.press()
        return
      }
      usedVoice = true
      open('converse')
    } else {
      session?.release()
    }
  }

  function stopAll(reason: EndReason = 'stop'): void {
    session?.end(reason)
    if (waiter) {
      timers.clearTimeout(waiter.timer)
      const w = waiter
      waiter = null
      w.resolve(null)
    }
  }

  return {
    start() {
      if (started) return
      started = true
      // With the flags off this does nothing at all: no bus listener, no timer, no network.
      if (!liveFlagOn(env)) return
      offBus = [
        d.bus.on('talk', (e) => onTalk(e)),
        d.bus.on('session:ended', () => stopAll('stop')),
      ]
      // The boot check of the configured model, once and off the press path. An unreachable network is not a failure of the model.
      if (liveFlagOn(env) && d.modelCheck) {
        void d.modelCheck().then(
          (r) => {
            modelState = r
            if (!r.ok && r.reason !== 'unreachable') log('live', `the configured Live model cannot be used (${r.reason}); voice stays off`)
          },
          () => undefined,
        )
      }
    },
    dispose() {
      started = false
      stopAll('stop')
      for (const off of offBus) off()
      offBus = []
      if (tickHandle !== null) timers.clearInterval(tickHandle)
      tickHandle = null
      listeners.clear()
    },
    status,
    subscribe(cb) {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    stopAll,
    workerUsedVoice: () => usedVoice,
    hasSession: () => session !== null && !session.isEnded,
    voiceAllowed: () => startRefusal() === null,
    startFromWake() {
      if (!liveFlagOn(env) || (session && !session.isEnded) || waiter) return false
      usedVoice = true
      return open('converse', undefined, true)
    },
    noteAnswer(id) {
      session?.noteAnswer(id)
    },
    listen(timeoutMs) {
      if (!liveFlagOn(env) || waiter || startRefusal() !== null) return Promise.resolve(null)
      return new Promise<string | null>((resolve) => {
        const w: NonNullable<typeof waiter> = {
          resolve,
          started: false,
          // Only the wait for the press has this limit; once the key is down the one-answer turn has its own caps.
          timer: timers.setTimeout(() => {
            if (waiter === w && !w.started) {
              waiter = null
              resolve(null)
            }
          }, Math.min(15_000, Math.max(1000, timeoutMs))),
        }
        waiter = w
      })
    },
  }
}
