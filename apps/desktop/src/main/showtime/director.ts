// Demo director (ALONGSIDE_DEMO_DIRECTOR=1, interactive demo only): removes luck from the ~90 s live demo.
//   - an always-on Live session (auto-start without a greeting, auto-restart after any drop, idle timeout off);
//   - six guaranteed beats on global shortcuts (and POST /tool demo_beat in dev) that run through the REAL tools and
//     overlay and make the assistant say fixed words, shown as a caption too, whatever the model understood;
//   - an instant, exact scam check: the real scam_check agent and chip plumbing, with the grounder replaced by the exact
//     boxes of the red-flag phrases on the staged bank note (apps/demo-stage __stage.scamRects).
// Absent in normal use, so real users are unaffected.
import os from 'node:os'
import { createAgentModelPort } from '../agents/model-port-adapter'
import { createAgents, type AgentRuntimeApi } from '../agents'
import { SKILLS } from '../teaching/skills/definitions'
import { LEVEL_LABEL } from '../teaching/levels'
import type { Services } from '../../shared/contracts'
import type { GroundResult, LearnerSnapshot, NormBox, PersonaId, ScamReport, SessionEndReason, SessionRequest, Shot, ToolResult } from '../../shared/protocol'
import type { Settings } from '../../shared/settings'
import type { Bus } from '../bus'
import type { ShowtimeDockView } from '../../shared/showtime'

export const DEMO_DIRECTOR_ENV = 'ALONGSIDE_DEMO_DIRECTOR'
export const isDirectorMode = (): boolean => process.env[DEMO_DIRECTOR_ENV] === '1'

export const BEATS = [1, 2, 3, 4, 5, 6] as const
export type Beat = (typeof BEATS)[number]

export const SHORTCUTS: Record<Beat, string> = {
  1: 'CommandOrControl+Alt+1',
  2: 'CommandOrControl+Alt+2',
  3: 'CommandOrControl+Alt+3',
  4: 'CommandOrControl+Alt+4',
  5: 'CommandOrControl+Alt+5',
  6: 'CommandOrControl+Alt+6',
}

export const GREETING = 'Hello, I am Marcus. What would you like to do?'
export const SETTINGS_LINE = 'Here is the Settings app, in the left column.'
export const GOODBYE = 'Goodbye, it was lovely helping you.'
export const SCAM_LINE = 'This looks like a scam. It rushes you with a two-hour threat and a lookalike link. Do not click it, and call the number on the back of your bank card.'
const LESSON_GOAL = 'video call my granddaughter Lily'
const SETTINGS_ICON = 'desk.icon.settings'
const POINT_IDS = ['point-ring', 'point-arrow']

const AUTO_START_DELAY_MS = 4000
const RESTART_DELAY_MS = 900
const LIVE_WAIT_MS = 9000
const FAREWELL_DELAY_MS = 5500

type ScamKey = 'urgent' | 'twoHours' | 'url' | 'phone'
export type ScamRects = Partial<Record<ScamKey, NormBox[]>>

// What the director needs from the practice desktop; absent (null) when it is not open.
export interface DirectorStage {
  scamRects(): Promise<ScamRects>
  rectOf(id: string): Promise<NormBox | null>
  // Opens a Messages conversation / closes an app on the practice desktop without resetting anything else.
  openThread(id: string): Promise<boolean>
  closeApp(app: string): Promise<boolean>
}

export interface DirectorDeps {
  bus: Pick<Bus, 'on' | 'emit'>
  state: { get(): { phase: string; persona: PersonaId | null }; patch(patch: { agents: import('../../shared/protocol').AgentChip[] } | { lastError: undefined }): void }
  settings: { get(): Settings }
  services: Pick<Services, 'overlay' | 'live' | 'learner' | 'capture' | 'grounder'>
  dispatch(name: string, args: unknown, source?: 'live' | 'debug'): Promise<ToolResult>
  showView(view: ShowtimeDockView): void
  stopSession(reason: SessionEndReason): void
  stage(): DirectorStage | null
  log(msg: string): void
  // Dev/test seams.
  sleep?: (ms: number) => Promise<void>
  now?: () => number
  setNoIdle?: () => void
}

export interface BeatResult {
  beat: Beat
  ok: boolean
  ms: number
  note?: string
}

const ACTIVE = new Set(['live', 'thinking', 'speaking'])

const DEMO_REPORT: ScamReport = {
  verdict: 'likely_scam',
  confidence: 0.98,
  redFlags: [
    { phrase: 'URGENT:', why: 'Rushes you before you can think' },
    { phrase: 'within 2 hours', why: 'A two-hour deadline is a pressure tactic' },
    { phrase: 'https://aldermoor-bank.secure-verify.co/login', why: 'A lookalike link, not your bank' },
    { phrase: '+44 7700 900482', why: 'A mobile number, not your bank card number' },
  ],
  advice: ['Do not click the link.', 'Call the number on the back of your bank card.'],
  humanHelp: 'Before you do anything, ring the number on the back of your bank card, or ask Age UK or someone you trust.',
  models: ['demo-director'],
  latencyMs: 1100,
}

const PHRASE_KEYS: Array<[RegExp, ScamKey]> = [
  [/urgent/i, 'urgent'],
  [/within 2 hours/i, 'twoHours'],
  [/^https?:|aldermoor-bank/i, 'url'],
  [/7700/, 'phone'],
]

export function unionBox(boxes: NormBox[]): NormBox | null {
  if (boxes.length === 0) return null
  return {
    xmin: Math.min(...boxes.map((b) => b.xmin)),
    ymin: Math.min(...boxes.map((b) => b.ymin)),
    xmax: Math.max(...boxes.map((b) => b.xmax)),
    ymax: Math.max(...boxes.map((b) => b.ymax)),
  }
}

const lcFirst = (s: string): string => (s ? s[0].toLowerCase() + s.slice(1) : s)

/** Two truthful sentences from the learner profile (no invented numbers). */
export function progressLine(snap: LearnerSnapshot): string {
  const skill = snap.skills.video_call
  const name = SKILLS.video_call.name.toLowerCase()
  const last = snap.lastSession?.summary?.trim().replace(/\.$/, '')
  const first = last && /^(found|did|started|finished|completed|opened|clicked|made)\b/i.test(last)
    ? `Last time you ${lcFirst(last)}.`
    : `You have practised to ${name} before.`
  const second = skill.level >= 3
    ? `You are at the "${LEVEL_LABEL[skill.level]}" level, so I am already helping you less.`
    : `You are at the "${LEVEL_LABEL[skill.level]}" level, and I will step back as you do it cleanly.`
  return `${first} ${second}`
}

export interface Director {
  /** Runs one beat now (serialised). Used by the shortcuts and by POST /tool demo_beat. */
  run(beat: Beat): Promise<BeatResult>
  /** Opens the always-on session a few seconds after the practice desktop is up. */
  onStageOpen(): void
  /** Dispatcher hook: returns undefined to let the normal tool run. */
  intercept(name: string, args: unknown): Promise<ToolResult | undefined>
  /** Make the assistant say exact words (also captioned). */
  say(text: string): void
  /** Keeps the session alive: call once at startup. Returns an unsubscribe. */
  dispose(): void
}

export function createDirector(deps: DirectorDeps): Director {
  const { bus, state, services: s, log } = deps
  const sleep = deps.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)))
  const now = deps.now ?? Date.now
  let farewell = false
  let disposed = false
  let restartTimer: ReturnType<typeof setTimeout> | null = null
  const restarts: number[] = []
  let queue: Promise<unknown> = Promise.resolve()
  let scamRects: ScamRects = {}

  const say = (text: string): void => {
    s.overlay.caption('assistant', text, true)
    s.live.inject(`[RUNNER] Say exactly these words and nothing else: "${text}"`, { interrupt: true })
  }

  const requestSession = (personaId: PersonaId): void => {
    deps.setNoIdle?.()
    const req: SessionRequest = { personaId, source: 'wake' } // 'wake' = no spoken opener: the first words are the presenter's
    bus.emit('session:request', req)
  }

  async function ensureSession(personaId: PersonaId): Promise<boolean> {
    farewell = false
    const st = state.get()
    if (!(ACTIVE.has(st.phase) && st.persona === personaId)) {
      if (!(st.phase === 'connecting' && st.persona === personaId)) requestSession(personaId)
    }
    const until = now() + LIVE_WAIT_MS
    while (now() < until) {
      const cur = state.get()
      if (ACTIVE.has(cur.phase) && cur.persona === personaId) {
        await sleep(350)
        return true
      }
      await sleep(150)
    }
    return false
  }

  // ----- scam beat: the real agent runtime, with the analyst and grounder swapped for exact local answers -----
  const stubShot = (): Shot => ({ id: 'demo-director', displayId: 0, widthPx: 1, heightPx: 1, scaleFactor: 1, jpegBase64: '', takenAt: now(), overlayHidden: false })
  const groundPhrase = async (target: string): Promise<GroundResult> => {
    const phrase = /"(.*)"\s*$/.exec(target)?.[1] ?? target
    const key = PHRASE_KEYS.find(([re]) => re.test(phrase))?.[1]
    const box = key ? unionBox(scamRects[key] ?? []) : null
    return box
      ? { found: true, box, confidence: 1, label: phrase, latencyMs: 0, model: 'demo-director' }
      : { found: false, confidence: 0, reason: 'not on the practice desktop', latencyMs: 0, model: 'demo-director' }
  }
  let runtime: AgentRuntimeApi | null = null
  const scamRuntime = (): AgentRuntimeApi => {
    if (runtime) return runtime
    runtime = createAgents({
      state: { patch: (p) => state.patch(p) },
      bus: { emit: (e, p) => bus.emit(e, p) },
      capture: { grab: async () => stubShot() },
      grounder: { ground: (req) => groundPhrase(req.target) },
      scam: {
        analyze: async (_req, opts) => {
          opts?.onProgress?.('Checking the message…')
          await sleep(1100)
          return DEMO_REPORT
        },
      },
      overlay: { show: (a) => s.overlay.show(a), clear: (ids) => s.overlay.clear(ids) },
      live: {
        inject: (text, opts) => {
          // The agent's own wording is "in your own words"; the demo needs the exact line, shown as a caption as well.
          if (/^\[AGENT_RESULT kind=scam_check [^\]]*status=done\]/.test(text)) return say(SCAM_LINE)
          s.live.inject(text, opts)
        },
      },
      learner: { snapshot: () => s.learner.snapshot() },
      settings: () => ({ ...deps.settings.get(), scamShield: true }),
      model: createAgentModelPort(),
      exportsDir: os.tmpdir(),
    })
    bus.on('tool:called', ({ name }) => {
      if (name === 'clear_annotations') runtime?.clearHighlights()
    })
    return runtime
  }

  const hasFlags = (r: ScamRects): boolean => Boolean(r.urgent && r.twoHours && r.url)

  /** Starts the exact scam check; undefined when the practice desktop or its boxes are unavailable (normal pipeline then). */
  async function startScam(): Promise<{ agentId: string } | undefined> {
    const stage = deps.stage()
    if (!stage) return undefined
    let rects = await stage.scamRects().catch(() => ({}) as ScamRects)
    if (!hasFlags(rects)) {
      // The bank message lives in the Messages app: bring its thread on screen, then wait for the render.
      await stage.openThread('scam').catch(() => false)
      for (let i = 0; i < 10 && !hasFlags(rects); i++) {
        await sleep(150)
        rects = await stage.scamRects().catch(() => ({}) as ScamRects)
      }
    }
    if (!hasFlags(rects)) return undefined
    scamRects = rects
    return scamRuntime().spawn('scam_check', 'Check the message from my bank on the screen', { useScreen: true })
  }

  async function pointAtSettings(): Promise<string> {
    s.overlay.clear([...POINT_IDS])
    runtime?.clearHighlights()
    const stage = deps.stage()
    let box = await stage?.rectOf(SETTINGS_ICON).catch(() => null)
    if (!box && stage) {
      // An open Messages window can cover the desktop icons: close it, then look again.
      await stage.closeApp('messages').catch(() => false)
      await sleep(400)
      box = await stage.rectOf(SETTINGS_ICON).catch(() => null)
    }
    if (box) {
      s.overlay.show([
        { id: 'point-ring', kind: 'ring', tone: 'guide', box, label: 'Settings' },
        { id: 'point-arrow', kind: 'arrow', tone: 'guide', to: box },
      ])
      return 'exact stage box'
    }
    const r = await deps.dispatch('point_at', { target: 'the grey Settings gear icon in the left column' }, 'debug')
    return `grounder: ${JSON.stringify(r).slice(0, 60)}`
  }

  const BEAT_FN: Record<Beat, () => Promise<string | undefined>> = {
    async 1() {
      if (!(await ensureSession('marcus'))) return 'session not live: said anyway'
      say(GREETING)
      return undefined
    },
    async 2() {
      await ensureSession('marcus')
      const r = await deps.dispatch('start_lesson', { goal: LESSON_GOAL }, 'debug')
      return JSON.stringify(r).slice(0, 80)
    },
    async 3() {
      await ensureSession('marcus')
      const r = await startScam()
      if (r) return `agent ${r.agentId}`
      const real = await deps.dispatch('spawn_agent', { kind: 'scam_check', task: 'Check the message from my bank on the screen', payload: { useScreen: true } }, 'debug')
      return `normal pipeline: ${JSON.stringify(real).slice(0, 60)}`
    },
    async 4() {
      await ensureSession('marcus')
      const how = await pointAtSettings()
      say(SETTINGS_LINE)
      return how
    },
    async 5() {
      await ensureSession('marcus')
      deps.showView('progress')
      const text = progressLine(await s.learner.snapshot())
      say(text)
      return text
    },
    async 6() {
      const live = await ensureSession('amelia')
      say(GOODBYE)
      farewell = true
      setTimeout(() => {
        deps.stopSession('goodbye')
      }, FAREWELL_DELAY_MS).unref?.()
      return live ? undefined : 'session not live: said anyway'
    },
  }

  const run = (beat: Beat): Promise<BeatResult> => {
    const job = queue.then(async (): Promise<BeatResult> => {
      const started = now()
      try {
        const note = await BEAT_FN[beat]()
        const ms = now() - started
        log(`beat ${beat} done in ${ms} ms${note ? ` (${note})` : ''}`)
        return { beat, ok: true, ms, ...(note ? { note } : {}) }
      } catch (err) {
        const ms = now() - started
        log(`beat ${beat} failed after ${ms} ms: ${err instanceof Error ? err.message : String(err)}`)
        return { beat, ok: false, ms, note: err instanceof Error ? err.message : String(err) }
      }
    })
    queue = job
    return job
  }

  // ----- always-on session -----
  const offEnded = bus.on('session:ended', ({ reason }) => {
    if (disposed || farewell || reason === 'stop' || reason === 'replaced') return
    state.patch({ lastError: undefined }) // never leave an error banner up: this restarts by itself
    if (restartTimer) return
    const t = now()
    while (restarts.length && t - restarts[0] > 30_000) restarts.shift()
    const delay = restarts.length >= 5 ? 5000 : RESTART_DELAY_MS
    restarts.push(t)
    log(`session ended (${reason}): reopening shortly`)
    restartTimer = setTimeout(() => {
      restartTimer = null
      if (disposed || farewell) return
      state.patch({ lastError: undefined })
      requestSession(state.get().persona ?? 'marcus')
    }, delay)
  })

  return {
    run,
    say,
    onStageOpen() {
      const timer = setTimeout(() => {
        if (disposed) return
        log('opening the always-on session (no greeting)')
        requestSession('marcus')
      }, AUTO_START_DELAY_MS)
      timer.unref?.()
    },
    async intercept(name, args) {
      if (name === 'demo_beat') {
        const raw = (args as { beat?: unknown } | null)?.beat
        const beat = Number(raw)
        if (!BEATS.includes(beat as Beat)) return { error: `demo_beat needs beat 1 to 6, got ${String(raw)}` } as ToolResult
        return (await run(beat as Beat)) as unknown as ToolResult
      }
      if (name === 'spawn_agent' && (args as { kind?: unknown } | null)?.kind === 'scam_check') {
        const r = await startScam()
        return r as ToolResult | undefined
      }
      return undefined
    },
    dispose() {
      disposed = true
      if (restartTimer) clearTimeout(restartTimer)
      offEnded()
      runtime?.dispose()
    },
  }
}

interface ScriptableWindow {
  isDestroyed(): boolean
  webContents: { executeJavaScript(code: string, userGesture?: boolean): Promise<unknown> }
}

/** The practice desktop as the director sees it: exact boxes straight from the page (screen space). */
export function stageFromWindow(getWin: () => ScriptableWindow | null): DirectorStage {
  const js = <T>(code: string): Promise<T> => {
    const win = getWin()
    if (!win || win.isDestroyed()) return Promise.reject(new Error('practice desktop is not open'))
    return win.webContents.executeJavaScript(code, true) as Promise<T>
  }
  return {
    scamRects: () => js<ScamRects>("__stage.scamRects({space:'screen'})"),
    rectOf: (id) => js<NormBox | null>(`__stage.rectOf(${JSON.stringify(id)}, {space:'screen'})`),
    openThread: (id) => js<boolean>(`__stage.openThread(${JSON.stringify(id)})`),
    closeApp: (app) => js<boolean>(`__stage.closeApp(${JSON.stringify(app)})`),
  }
}

/** Registers the six global shortcuts (each failure is logged and tolerated). Returns the unregister function. */
export async function registerDirectorShortcuts(director: Pick<Director, 'run'>, log: (msg: string) => void): Promise<() => void> {
  const { globalShortcut } = await import('electron')
  const done: string[] = []
  for (const beat of BEATS) {
    const accel = SHORTCUTS[beat]
    try {
      const ok = globalShortcut.register(accel, () => void director.run(beat))
      if (ok) done.push(accel)
      else log(`shortcut ${accel} could not be registered (taken by another app)`)
    } catch (err) {
      log(`shortcut ${accel} failed: ${err instanceof Error ? err.message : String(err)}`)
    }
  }
  log(`shortcuts ready: ${done.length}/${BEATS.length} (Option+Command+1..6)`)
  return () => {
    for (const a of done) {
      try {
        globalShortcut.unregister(a)
      } catch {
        // already gone
      }
    }
  }
}
