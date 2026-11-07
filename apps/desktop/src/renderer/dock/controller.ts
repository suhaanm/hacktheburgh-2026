// Dock-side wiring: owns the Live session lifecycle and the single-owner microphone arbitration with the wake spotter.
//   session:start (wake/hotkey/button) -> pause spotter -> LiveSession (persona voice + teaching system instruction)
//   Live -> main: live:transcript (captions), live:status (phase), live:toolCall (tools), session:ended (idle/goodbye/stop/error)
//   main -> Live: live:inject (stage directions), session:stop
// Not UI: DESIGN owns the rest of src/renderer/dock.
import { MODELS } from '../../shared/models'
import { DEFAULT_PERSONA, PERSONAS, PERSONA_LIST } from '../../shared/personas'
import type { PersonaConfig } from '../../shared/personas'
import type { CompanionState, LiveStatus, SessionEndReason, SessionRequest } from '../../shared/protocol'
import { AudioPlayer, LiveSession, MicCapture, pcm16ToBase64Chunks } from '../live'
import type { LiveAuth, LivePhase } from '../live'
import { createWakeSpotter } from '../wake'
import type { WakeSpotter } from '../wake'
import { chatBus } from './chat/bus'
import type { ChatMessage } from './chat/bus'

const IDLE_MS = 20_000
// During a lesson the learner is busy on their own screen, so silence is expected.
const LESSON_IDLE_MS = 120_000
// Someone typing in the chat takes their time; the session (and screen reading) still ends after 5 quiet minutes.
const TEXT_IDLE_MS = 300_000
// Used while personas carry voiceName 'TBD' (set by the voice audition). Both verified accepted by gemini-3.8-live.
const FALLBACK_VOICE = { male: 'Charon', female: 'Sulafat' } as const
const OPENING_BY_BUTTON = '[RUNNER] The learner opened this session with a button press, not by speaking. Greet them in one short sentence and ask what they would like help with.'

class MockLiveError extends Error {}

export interface LiveHandle {
  // 0..1 smoothed levels for the orb / listening light; 0 when no session.
  outputLevel(): number
  inputLevel(): number
  active(): boolean
}

let handle: LiveHandle = { outputLevel: () => 0, inputLevel: () => 0, active: () => false }
// DESIGN polls this (rAF) to animate the orb; stable reference for the lifetime of the dock.
export const liveHandle: LiveHandle = {
  outputLevel: () => handle.outputLevel(),
  inputLevel: () => handle.inputLevel(),
  active: () => handle.active(),
}

export function resolveVoice(p: PersonaConfig): string {
  return p.voiceName && p.voiceName !== 'TBD' ? p.voiceName : FALLBACK_VOICE[p.gender]
}

function mapPhase(p: LivePhase): LiveStatus['phase'] | null {
  switch (p) {
    case 'connecting':
    case 'live':
    case 'thinking':
    case 'speaking':
    case 'error':
      return p
    default:
      return null
  }
}

export interface ControllerOptions {
  // Tests/dev: skip the wake spotter (hotkey and button paths never touch it anyway).
  wake?: boolean
}

export function startController(opts: ControllerOptions = {}): () => void {
  const api = window.alongside
  let session: LiveSession | null = null
  let mockActive = false
  let current: CompanionState | null = null
  let spotter: WakeSpotter | null = null
  // The banner text we set when the spotter was unavailable, so we clear exactly that (and nothing else) on recovery.
  let wakeError: string | null = null
  // Chat: typed turns wait here while a session is being opened for them; pendingChat tells begin() it was a typed start.
  const typedQueue: string[] = []
  let pendingChat: { textOnly: boolean } | null = null
  let chatStarting = false
  let sessionNo = 0
  const idleFor = (): number => (safeLocalStorage('alongside.noIdle') === '1' ? 0 : chatBus.mode() === 'text' ? TEXT_IDLE_MS : current?.skill ? LESSON_IDLE_MS : IDLE_MS)
  let beginSeq = 0
  // True from a session request until it ends; lets a begin() that lost the race to Stop give the mic back to the spotter.
  let liveRequested = false
  const cleanups: Array<() => void> = []
  // Sessions whose end must not be reported to main (replaced by a newer one, which main is already setting up).
  const silenced = new WeakSet<LiveSession>()

  const log = (...a: unknown[]) => console.log('[live]', ...a)

  // ---------- state mirror ----------
  const applyState = (next: CompanionState): void => {
    current = next
    session?.setMicMuted(next.micMuted)
    session?.setIdleTimeout(idleFor())
    spotter?.setSettings({ wakeEnabled: next.settings.wakeEnabled, pushToTalkOnly: next.settings.pushToTalkOnly, micMuted: next.micMuted })
  }
  void api.getState().then(applyState).catch((err: unknown) => log('getState failed', err))
  cleanups.push(api.onState(applyState))

  // ---------- wake spotter (mic owner while no Live session) ----------
  const wakeSettings = (): { wakeEnabled: boolean; pushToTalkOnly: boolean; micMuted: boolean } | undefined => {
    const c = current as CompanionState | null
    return c ? { wakeEnabled: c.settings.wakeEnabled, pushToTalkOnly: c.settings.pushToTalkOnly, micMuted: c.micMuted } : undefined
  }
  if (opts.wake !== false) {
    try {
      spotter = createWakeSpotter({
        personas: PERSONA_LIST,
        getToken: () => api.wake.getToken(),
        settings: wakeSettings(),
        onWake: (e) => api.wakeDetected({ personaId: e.personaId, source: 'wake' }),
        onStatus: (s) => {
          if (session || mockActive) return
          const phase = current?.phase
          if (phase === 'connecting' || phase === 'live' || phase === 'thinking' || phase === 'speaking' || phase === 'error') return
          const recovered = s.state !== 'unavailable' && wakeError !== null && current?.lastError === wakeError
          if (s.state === 'unavailable') wakeError = s.detail ?? null
          void api.patchState({
            phase: s.listening ? 'listening_for_name' : s.state === 'unavailable' ? 'asleep' : (phase ?? 'asleep'),
            ...(s.state === 'unavailable' ? { lastError: s.detail } : recovered ? { lastError: undefined } : {}),
          })
          if (recovered) wakeError = null
        },
      })
      void spotter.start().catch((err: unknown) => log('wake spotter failed to start', err))
      cleanups.push(() => spotter?.dispose())
    } catch (err) {
      log('wake spotter unavailable', err)
    }
  }

  // ---------- Live session ----------
  async function begin(req: SessionRequest): Promise<void> {
    if (session || mockActive) await endSession('replaced', true)
    const seq = ++beginSeq
    liveRequested = true
    mockActive = false
    const chat = pendingChat
    pendingChat = null
    // A spoken start (wake word, hotkey, button) means the learner wants voice, whatever the chat was set to.
    if (!chat && chatBus.mode() === 'text') chatBus.setMode('voice')
    const textOnly = chat ? chat.textOnly : false
    const myNo = ++sessionNo
    let uIdx = 0
    let aIdx = 0
    spotter?.pause('live')
    const persona = PERSONAS[req.personaId]
    let firstToken: LiveAuth | null
    try {
      const t = await api.live.getToken(req.personaId)
      if (t.token === 'mock') throw new MockLiveError('Live voice needs a real GEMINI_API_KEY (mock mode)')
      firstToken = { kind: 'token', value: t.token }
    } catch (err) {
      spotter?.resume('live')
      if (err instanceof MockLiveError) {
        // Mock mode (no key): keep the loop observable without a voice; the debug HTTP / dock buttons still drive tools.
        mockActive = true
        handle = { outputLevel: () => 0, inputLevel: () => 0, active: () => true }
        api.live.status({ connected: true, phase: 'live' })
        api.live.transcript({ role: 'assistant', text: 'Voice is off in mock mode. Add GEMINI_API_KEY to use the real voice.', final: true })
        for (const _ of typedQueue.splice(0)) mockChatReply()
        chatStarting = false
        log('mock mode: no Live voice')
      } else {
        const message = err instanceof Error ? err.message : String(err)
        void api.patchState({ lastError: friendlyError(message) })
        api.sessionEnded('error')
      }
      typedQueue.length = 0
      chatStarting = false
      return
    }
    if (seq !== beginSeq) {
      if (!liveRequested) spotter?.resume('live') // Stop arrived while the token was being minted
      chatStarting = false
      return
    }

    const s = new LiveSession({
      host: {
        getAuth: () => {
          // Reconnects and GoAway handovers mint a fresh single-use token.
          if (firstToken) {
            const t = firstToken
            firstToken = null
            return Promise.resolve(t)
          }
          return api.live.getToken(req.personaId).then((t): LiveAuth => ({ kind: 'token', value: t.token }))
        },
        systemInstruction: () => api.live.systemInstruction(req.personaId),
      },
      audioIn: new MicCapture(),
      audioOut: new AudioPlayer(),
      model: MODELS.live,
      toolHandler: (call) => api.live.toolCall({ id: call.id, name: call.name, args: call.args }),
      frames: { grab: () => api.live.liveFrame() },
      idleTimeoutMs: current?.skill ? LESSON_IDLE_MS : IDLE_MS,
      duplex: await chooseDuplex(),
      log: (...a) => log(...a),
    })
    session = s
    handle = { outputLevel: () => s.getOutputLevel(), inputLevel: () => s.getInputLevel(), active: () => true }
    s.setMicMuted(current?.micMuted ?? false)
    s.on('state', (st) => {
      if (session !== s) return
      const phase = st.reconnecting ? 'connecting' : mapPhase(st.phase)
      if (phase) api.live.status({ connected: st.connected, phase })
    })
    s.on('transcript', (t) => {
      if (session !== s) return
      api.live.transcript(t)
      const idx = t.role === 'user' ? uIdx : aIdx
      const m: ChatMessage = { id: `${t.role === 'user' ? 'u' : 'a'}-${myNo}-${idx}`, role: t.role, text: t.text, final: t.final, at: Date.now(), via: 'voice' }
      chatBus.push(m)
      if (t.final) t.role === 'user' ? uIdx++ : aIdx++
    })
    s.on('notice', (n) => {
      log('notice', n.kind, n.message)
      if (n.kind === 'mic_unavailable') {
        void api.patchState({ lastError: friendlyError('getUserMedia NotAllowedError') })
        chatBus.setMode('text') // no microphone: the chat is how they talk to us
      }
    })
    s.on('error', (e) => {
      log('error', e.message)
      void api.patchState({ lastError: friendlyError(e.message) })
    })
    s.on('resumption', (r) => r.reconnected && log('reconnected', r.resumed ? '(resumed)' : '(fresh session)'))
    s.on('ended', ({ reason }) => {
      if (session === s) {
        session = null
        handle = { outputLevel: () => 0, inputLevel: () => 0, active: () => false }
      }
      spotter?.resume('live')
      if (!silenced.has(s)) api.sessionEnded(reason)
    })

    try {
      await s.start({
        voiceName: resolveVoice(persona),
        textOnly,
        micOptional: true,
        opening: req.source === 'wake' || chat ? undefined : OPENING_BY_BUTTON,
        takePreRoll: () => {
          // Always taken (it releases the spotter's mic), but only a wake means those words were meant for us: after a hotkey or
          // button press the buffer is just room audio.
          const pcm = spotter?.takePreroll() ?? null
          return req.source === 'wake' && pcm && pcm.length ? pcm16ToBase64Chunks(pcm) : null
        },
      })
      if (seq !== beginSeq) {
        silenced.add(s)
        await s.stop('replaced')
      } else {
        s.setIdleTimeout(idleFor())
        if (chatBus.mode() === 'text') void s.setTextMode(true)
        for (const text of typedQueue.splice(0)) s.sendUserText(text)
      }
    } catch (err) {
      typedQueue.length = 0
      log('start failed', err instanceof Error ? err.message : err)
    } finally {
      chatStarting = false
    }
  }

  // ---------- chat (typed turns share the Live session with voice) ----------
  function mockChatReply(): void {
    chatBus.push({ id: `a-mock-${Date.now()}`, role: 'assistant', text: 'Chat replies need a real GEMINI_API_KEY (mock mode).', final: true, at: Date.now(), via: 'voice' })
  }

  function sendTyped(text: string): void {
    if (session?.sendUserText(text)) return
    if (mockActive) return mockChatReply()
    typedQueue.push(text) // session still connecting, or none yet
    if (session || chatStarting) return
    chatStarting = true
    pendingChat = { textOnly: chatBus.mode() === 'text' }
    // Through main like every other start, so phase/state stay consistent for the dock and overlay.
    api.wakeDetected({ personaId: current?.persona ?? DEFAULT_PERSONA, source: 'button' })
  }

  async function endSession(reason: SessionEndReason, silent: boolean): Promise<void> {
    beginSeq++ // invalidates a begin() still waiting for its token
    if (reason !== 'replaced') liveRequested = false
    if (mockActive) {
      mockActive = false
      handle = { outputLevel: () => 0, inputLevel: () => 0, active: () => false }
      spotter?.resume('live')
      if (!silent) api.sessionEnded(reason)
      return
    }
    const s = session
    if (!s) return
    if (silent) silenced.add(s)
    await s.stop(reason)
  }

  cleanups.push(chatBus.onSend((text) => sendTyped(text)))
  cleanups.push(
    chatBus.onMode((m) => {
      session?.setIdleTimeout(idleFor())
      void session?.setTextMode(m === 'text')
      // Text mode means the microphone is off for the wake spotter too.
      if (m === 'text') spotter?.pause('manual')
      else spotter?.resume('manual')
    }),
  )
  cleanups.push(api.onSessionStart((req) => void begin(req)))
  cleanups.push(api.onSessionStop((reason) => void endSession(reason, reason === 'replaced')))
  cleanups.push(
    api.live.onInject(({ text, interrupt }) => {
      if (!session) return
      session.injectText(text, { interrupt: interrupt === true })
    }),
  )

  return () => {
    for (const c of cleanups) c()
    void session?.stop('stop')
  }
}

// Built-in laptop speakers next to an open mic is the classic self-interruption loop, so the mic is not uploaded while the
// assistant speaks there. Headphones/headsets keep full duplex (barge-in). Override: localStorage 'alongside.duplex' = half|full.
// If the default output is unknown, full duplex starts and the session's echo guard switches itself to half on the first echo.
async function chooseDuplex(): Promise<'full' | 'half'> {
  const forced = safeLocalStorage('alongside.duplex')
  if (forced === 'half' || forced === 'full') return forced
  try {
    const outs = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === 'audiooutput')
    const label = (outs.find((d) => d.deviceId === 'default') ?? outs[0])?.label ?? ''
    if (/head(phone|set)|airpods|buds|bluetooth|usb|hdmi|display|monitor/i.test(label)) return 'full'
    if (/speaker|built-?in|macbook|imac/i.test(label)) return 'half'
  } catch {
    /* labels unavailable */
  }
  return 'full'
}

function safeLocalStorage(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

// Plain words for the dock; the raw text stays in the console.
function friendlyError(raw: string): string {
  if (/microphone|getUserMedia|NotAllowed|Permission/i.test(raw)) return 'I cannot hear you: the microphone is blocked. Allow it in System Settings, then try again.'
  if (/token|auth|API key|403|401/i.test(raw)) return 'I could not connect: the API key was refused.'
  if (/timed out|network|closed|lost|connection/i.test(raw)) return 'I lost the connection. Check the internet and say my name again.'
  return `Something went wrong: ${raw.slice(0, 120)}`
}
