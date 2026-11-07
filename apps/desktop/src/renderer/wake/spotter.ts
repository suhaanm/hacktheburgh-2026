import { createMicAudioSource } from './audio-source'
import { createGeminiEngineFactory } from './engine-gemini'
import { createWakeMatcher, normalize, type WakePersona } from './matcher'
import { PrerollBuffer, PCM_SAMPLE_RATE } from './preroll'
import type {
  WakeAudioSource,
  WakeEngine,
  WakeEngineFactory,
  WakeEngineHandlers,
  WakePauseReason,
  WakeSettings,
  WakeSpotter,
  WakeSpotterOptions,
  WakeStatus,
} from './types'

const MAX_FAILURES = 6
// While unavailable the spotter keeps trying quietly, so a returning network or a granted permission recovers it.
const RECOVERY_MS = 20_000
const HANDOFF_LEAD_MS = 1500
// If a wake fires but nobody pauses us for a Live session within this long, listen again.
const WAKE_ORPHAN_MS = 15000

function vocabularyFrom(personas: readonly WakePersona[], prefixes: readonly string[]): string[] {
  const skip = new Set(prefixes)
  const words = new Set<string>()
  for (const p of personas) {
    for (const phrase of p.wakePhrases) {
      const core = normalize(phrase)
        .split(' ')
        .filter((w) => w && !skip.has(w))
        .join(' ')
      if (core) words.add(core)
    }
  }
  return [...words]
}

export function createWakeSpotter<Id extends string>(options: WakeSpotterOptions<Id>): WakeSpotter<Id> {
  const cooldownMs = options.cooldownMs ?? 4000
  const handoffMs = options.handoffMs ?? 6000
  const maxSessionMs = options.maxSessionMs ?? 540_000
  const stableInterimMs = options.stableInterimMs ?? 1200
  const ring = new PrerollBuffer(options.prerollMs ?? 3000)
  const settings: WakeSettings = { wakeEnabled: true, pushToTalkOnly: false, micMuted: false, ...options.settings }
  const manual = new Set<WakePauseReason>()

  let personas = options.personas
  let matcher = createWakeMatcher(personas, options.matcher)
  let factory: WakeEngineFactory | null = options.createEngine ?? null
  const ensureFactory = (): WakeEngineFactory | null => {
    if (factory) return factory
    if (!options.getToken) return null
    factory = createGeminiEngineFactory({ getToken: options.getToken, vocabulary: vocabularyFrom(personas, options.matcher?.prefixes ?? ['hey', 'hay', 'hi', 'ok', 'okay', 'hello']) })
    return factory
  }

  let started = false
  let disposed = false
  let connecting = false
  let recheck = false
  let rotating = false
  let failures = 0
  let audio: WakeAudioSource | null = null
  let audioStarting: Promise<void> | null = null
  let engine: WakeEngine | null = null
  let engineReady = false
  let streamStartedAt = 0
  let lastWakeAt = -Infinity
  let lastTranscriptAt = 0
  let stable: { key: string; since: number } | null = null
  let retryTimer: ReturnType<typeof setTimeout> | null = null
  let rotateTimer: ReturnType<typeof setTimeout> | null = null
  let wakeTimer: ReturnType<typeof setTimeout> | null = null
  let handoffTimer: ReturnType<typeof setTimeout> | null = null
  let handoff: Int16Array[] | null = null
  let lastStatusJson = ''
  let status: WakeStatus = { state: 'off', listening: false, pausedFor: [], cloud: true, engine: 'gemini-transcribe-live' }

  const pausedFor = (): WakePauseReason[] => {
    const r = new Set(manual)
    if (!settings.wakeEnabled) r.add('disabled')
    if (settings.pushToTalkOnly) r.add('push-to-talk-only')
    if (settings.micMuted) r.add('muted')
    return [...r]
  }

  const emit = (state: WakeStatus['state'], detail?: string): void => {
    status = { state, listening: state === 'listening', pausedFor: pausedFor(), cloud: true, engine: 'gemini-transcribe-live', ...(detail ? { detail } : {}) }
    const json = JSON.stringify(status)
    if (json === lastStatusJson) return
    lastStatusJson = json
    options.onStatus?.(status)
  }

  const clear = (t: ReturnType<typeof setTimeout> | null): null => {
    if (t) clearTimeout(t)
    return null
  }

  function onPcm(pcm: Int16Array): void {
    ring.push(pcm)
    if (handoff) handoff.push(pcm)
    if (engine && engineReady) engine.send(pcm)
  }

  async function ensureAudio(): Promise<void> {
    if (audio) return audioStarting ?? undefined
    const src = (options.createAudioSource ?? (() => createMicAudioSource(options.getStream)))()
    audio = src
    audioStarting = src.start(onPcm)
    try {
      await audioStarting
    } catch (e) {
      if (audio === src) audio = null
      throw e
    } finally {
      audioStarting = null
    }
  }

  function releaseAudio(): void {
    audio?.stop()
    audio = null
    audioStarting = null
    ring.clear()
  }

  function dropEngine(): void {
    rotateTimer = clear(rotateTimer)
    retryTimer = clear(retryTimer)
    const e = engine
    engine = null
    engineReady = false
    rotating = false
    e?.stop()
  }

  function makeEngine(): WakeEngine {
    const f = ensureFactory()
    if (!f) throw new Error('No wake engine configured (needs getToken)')
    let self: WakeEngine | null = null
    const current = (): boolean => self !== null && self === engine
    const handlers: WakeEngineHandlers = {
      onReady() {
        if (!current()) return
        engineReady = true
        failures = 0
        streamStartedAt = Date.now()
        emit('listening')
        scheduleRotate()
      },
      onTranscript(text, final) {
        if (current()) handleTranscript(text, final)
      },
      onError(error, fatal) {
        if (current()) fail(error, fatal)
      },
      onGoAway() {
        if (current()) void rotate()
      },
    }
    self = f(handlers)
    return self
  }

  function shouldListen(): boolean {
    return started && !disposed && pausedFor().length === 0
  }

  type FailureKind = 'net' | 'mic' | 'config'

  // `detail` is shown to the user verbatim, so it is always plain English; the raw error only goes to the console.
  function fail(error: Error, fatal: boolean, kind: FailureKind = 'net'): void {
    console.warn('[wake]', kind, error)
    dropEngine()
    failures++
    if (!shouldListen()) return
    if (fatal || failures > MAX_FAILURES) {
      releaseAudio()
      emit(
        'unavailable',
        kind === 'mic'
          ? 'Voice activation needs microphone permission, or no microphone was found. Use the button or the keyboard shortcut.'
          : 'Voice activation is unavailable right now. Use the button or the keyboard shortcut.',
      )
      if (kind !== 'config') scheduleRecovery(kind)
      return
    }
    emit('reconnecting', 'Reconnecting to the voice service.')
    retryTimer = setTimeout(() => {
      retryTimer = null
      if (shouldListen() && !engine) void connect()
    }, Math.min(500 * 2 ** (failures - 1), 8000))
  }

  // Network trouble is probed with a token request only, so the microphone is not opened while the cloud is unreachable.
  function scheduleRecovery(kind: Exclude<FailureKind, 'config'>): void {
    retryTimer = clear(retryTimer)
    retryTimer = setTimeout(() => {
      retryTimer = null
      if (!shouldListen() || engine || connecting) return
      if (kind === 'net' && options.getToken) {
        options.getToken().then(
          () => {
            if (shouldListen() && !engine && !connecting) void connect()
          },
          () => {
            if (shouldListen() && !engine && !connecting) scheduleRecovery('net')
          },
        )
        return
      }
      void connect()
    }, RECOVERY_MS)
  }

  async function connect(): Promise<void> {
    if (connecting) return
    connecting = true
    if (status.state !== 'unavailable') emit(failures ? 'reconnecting' : 'starting')
    try {
      try {
        await ensureAudio()
      } catch (e) {
        const denied = e instanceof Error && (e.name === 'NotAllowedError' || e.name === 'SecurityError')
        fail(e instanceof Error ? e : new Error(String(e)), denied, 'mic')
        return
      }
      if (!shouldListen()) return
      let eng: WakeEngine
      try {
        eng = makeEngine()
      } catch (e) {
        fail(e instanceof Error ? e : new Error(String(e)), true, 'config')
        return
      }
      engine = eng
      try {
        await eng.start()
      } catch (e) {
        if (engine === eng) fail(e instanceof Error ? e : new Error(String(e)), false)
        else eng.stop()
        return
      }
      if (engine !== eng) eng.stop()
    } finally {
      connecting = false
      // State may have changed while connecting (paused, then resumed).
      if (recheck) {
        recheck = false
        reconcile()
      }
    }
  }

  function scheduleRotate(): void {
    rotateTimer = clear(rotateTimer)
    rotateTimer = setTimeout(function tick() {
      rotateTimer = null
      if (!engine) return
      if (Date.now() - lastTranscriptAt < 2000) rotateTimer = setTimeout(tick, 2000)
      else void rotate()
    }, maxSessionMs)
  }

  // Open the next stream before closing the old one so there is no deaf gap at the 10-minute connection cap.
  async function rotate(): Promise<void> {
    const old = engine
    const f = ensureFactory()
    if (!old || !f || rotating) return
    rotating = true
    let next = null as WakeEngine | null
    let giveUp: ReturnType<typeof setTimeout> | null = null
    try {
      const swapped = new Promise<void>((resolve, reject) => {
        giveUp = setTimeout(() => reject(new Error('rotation timed out')), 8000)
        const handlers: WakeEngineHandlers = {
          onReady: () => resolve(),
          onTranscript: (text, final) => {
            if (engine === next) handleTranscript(text, final)
          },
          onError: (error, fatal) => {
            if (engine === next) fail(error, fatal)
            else reject(error)
          },
          onGoAway: () => {
            if (engine === next) void rotate()
          },
        }
        next = f(handlers)
        next.start().catch(reject)
      })
      await swapped
      giveUp = clear(giveUp)
      if (engine !== old || !next) {
        next?.stop()
        return
      }
      engine = next
      old.stop()
      streamStartedAt = Date.now()
      scheduleRotate()
    } catch {
      next?.stop()
      // Keep the old stream; it either survives or errors into the normal reconnect path.
      rotateTimer = setTimeout(() => void rotate(), 10_000)
    } finally {
      giveUp = clear(giveUp)
      rotating = false
    }
  }

  function handleTranscript(text: string, final: boolean): void {
    const now = Date.now()
    lastTranscriptAt = now
    options.onDebug?.(text, final)
    // The server keeps repeating an unchanged interim and can be slow to finalise; an interim that has stood
    // unchanged long enough is the end of an utterance, which lets a bare "Amelia." (ASR dropped "hey") count.
    const key = normalize(text)
    let settled = final
    if (final) stable = null
    else if (stable?.key === key) settled = now - stable.since >= stableInterimMs
    else stable = { key, since: now }
    const m = matcher.match(text, { final: settled })
    if (!m) return
    if (now - lastWakeAt < cooldownMs) return
    lastWakeAt = now
    // Stop streaming to the cloud immediately; keep capturing locally for the Live handoff pre-roll.
    beginHandoff()
    manual.add('live')
    wakeTimer = clear(wakeTimer)
    wakeTimer = setTimeout(() => {
      wakeTimer = null
      manual.delete('live')
      reconcile()
    }, WAKE_ORPHAN_MS)
    stable = null
    const atMs = now - streamStartedAt
    reconcile()
    options.onWake({ personaId: m.personaId as Id, source: 'wake', score: m.score, heard: m.heard, trailing: m.trailing, atMs })
  }

  function beginHandoff(): void {
    const lead = Math.round((HANDOFF_LEAD_MS / 1000) * PCM_SAMPLE_RATE)
    const recent = ring.snapshot()
    handoff = [recent.subarray(Math.max(0, recent.length - lead))]
    handoffTimer = clear(handoffTimer)
    handoffTimer = setTimeout(endHandoff, handoffMs)
  }

  function endHandoff(): void {
    handoffTimer = clear(handoffTimer)
    handoff = null
    reconcile()
  }

  function reconcile(): void {
    if (disposed) return
    if (shouldListen()) {
      if (connecting) recheck = true
      else if (!engine && !retryTimer) void connect()
      return
    }
    if (connecting) recheck = true
    dropEngine()
    const reasons = pausedFor()
    // A text-to-speech pause keeps the mic warm (local only) so listening resumes instantly; everything else releases it.
    const keepMic = started && reasons.length > 0 && reasons.every((r) => r === 'tts')
    if (!keepMic && !handoff) releaseAudio()
    emit(started ? 'paused' : 'off')
  }

  function stopAll(): void {
    started = false
    wakeTimer = clear(wakeTimer)
    handoff = null
    handoffTimer = clear(handoffTimer)
    manual.clear()
    dropEngine()
    releaseAudio()
    emit('off')
  }

  return {
    async start() {
      if (disposed) return
      started = true
      failures = 0
      if (shouldListen()) await connect()
      else reconcile()
    },
    stop: stopAll,
    pause(reason = 'manual') {
      manual.add(reason)
      if (reason === 'live') wakeTimer = clear(wakeTimer)
      reconcile()
    },
    resume(reason = 'manual') {
      manual.delete(reason)
      if (reason === 'live') {
        wakeTimer = clear(wakeTimer)
        handoff = null
        handoffTimer = clear(handoffTimer)
        lastWakeAt = Date.now()
      }
      reconcile()
    },
    dispose() {
      if (disposed) return
      stopAll()
      disposed = true
    },
    takePreroll() {
      if (handoff) {
        const total = handoff.reduce((n, c) => n + c.length, 0)
        const out = new Int16Array(total)
        let pos = 0
        for (const c of handoff) {
          out.set(c, pos)
          pos += c.length
        }
        endHandoff()
        return total ? out : null
      }
      if (!audio) return null
      const snap = ring.snapshot()
      return snap.length ? snap : null
    },
    setSettings(patch) {
      // The dock calls this on every state update; only a real change may touch the connection.
      const changed = (Object.keys(patch) as (keyof WakeSettings)[]).some((k) => patch[k] !== undefined && settings[k] !== patch[k])
      Object.assign(settings, patch)
      if (started && changed) {
        if (shouldListen() && status.state === 'unavailable') failures = 0
        reconcile()
      }
    },
    setPersonas(next) {
      personas = next
      matcher = createWakeMatcher(personas, options.matcher)
    },
    getStatus: () => status,
  }
}
