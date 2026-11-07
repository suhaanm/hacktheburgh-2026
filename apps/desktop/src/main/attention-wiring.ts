// The attention layer wired into the desktop shell (REQ-8). This is the ONLY glue: main/index.ts makes one call after the shell objects exist,
//     const attentionWiring = wireAttention({ ...shell objects, as plain functions and objects... })      (dispose in will-quit)
// and passes `attentionWiring?.cuePort` as `attention` to the Cue controller. Everything the layer needs from the shell arrives as a parameter, so
// the whole thing runs and is tested without Electron. Off unless the flag is on (attention/flags.ts): then this returns null, creates no timer
// and makes no request, and every optional hook it would have bound stays unbound, so each file keeps its old behaviour.
//
// What it does, in the order of the lead's list:
//   1. starts the layer (`startAttention`) with the worker's signals, the ports below, the kill state and the producer sources;
//   2. signals(): input rhythm from timestamps only (never which key), presence and task state from the break signals proposals.ts already
//      has, quiet and pause from settings, screen sharing and calls from the awareness probes (false when unknown), the rest from getters;
//   3. ports: a notice is drawn by the HUD (above the Stop all pill), its buttons come back as HUD actions, the counts go to the menu bar, and
//      an action id becomes a dashboard page (`dashboardUrl`; the layer never builds a URL);
//   4. producers: the kill switch (raise on engage, resolve on clear), the help-level glance (asks before it draws), proposals;
//   5. permission prompts take only the LOCAL lock (never gated or delayed by the router);
//   6. the producer bridge's sources: small read-only loopback fetchers, a failed read answers null (the bridge then changes nothing).
import {
  attentionEnabled,
  createFlowTracker,
  startAttention,
  type ActionId,
  type AttentionBadges,
  type AttentionClient,
  type AttentionHandle,
  type AttentionPorts,
  type AttentionSignals,
  type CueAttentionPort,
  type NoticeView,
  type ProducerSources,
  type QueueItemView,
  type RunView,
  type VoiceLock,
} from './attention'
import type { ChipDriver } from './coach-chip'
import { dashboardUrl, isLoopbackUrl, type DashboardRoute, type Endpoints } from './engine/endpoints'
import type { HudModel, HudNoticeSink } from './hud-model'
import type { HudNotice } from '../shared/hud'
import type { KillSwitch } from './kill-switch'
import type { BreakSignals, ProposalScheduler } from './proposals'
import type { ToastHandle } from './toast'
import type { ShellTray, TrayAttention } from './tray'

/** The worker is away after this long without input (system idle time). */
export const AWAY_AFTER_S = 300
/** The slow probes (screen sharing, a call) are read at most this often. */
export const PROBE_EVERY_MS = 10_000

/** What the signals need from the break signals proposals.ts already builds (a full `BreakSignals` fits). */
export type AttentionBreakSignals = Pick<BreakSignals, 'idleSeconds' | 'locked' | 'task' | 'lastEpisodeEndAt'>
/** A yes/no reading the awareness layer has (screen sharing, a call). null or undefined means unknown, which is read as no. */
export type Probe = () => boolean | null | undefined | Promise<boolean | null | undefined>

export interface AttentionWiringDeps {
  /** core.endpoints: the loopback base URLs (the engine hosts the attention routes, the queue, the briefing and the routines). */
  endpoints: Pick<Endpoints, 'engine' | 'agent' | 'dashboard'>
  /** The engine identity's person id (`() => core.engine.identity.person`). */
  person: () => string | null
  /** The settings store: Cue's quiet-until and the menu's pause-until make `dnd`. */
  settings: { get(): { cueQuietUntil: number | null; pausedUntil: number | null } }
  /** understudy.hudModel: draws the notice and sends its buttons back. */
  hudModel: Pick<HudModel, 'setNotice' | 'setAttention' | 'state'>
  /** Opens a URL in the worker's browser (`shell.openExternal`). Only ever called with dashboard URLs. */
  openExternal(url: string): void
  /** understudy.kill: its state drives the producers; the pill and the menu stay driven by the kill switch itself. */
  kill: Pick<KillSwitch, 'isKilled' | 'subscribe'>
  /** The break signals proposals.ts builds: idle time, the screen lock, the engine's task and when the last episode ended. */
  breakSignals?: () => AttentionBreakSignals | null
  /** System idle seconds, used only when there are no break signals. */
  idleSeconds?: () => number
  /** Input timestamps and nothing else (never which key): a click or a key at `tMs`. Returns the unsubscribe. */
  inputTimes?: (cb: (tMs: number) => void) => () => void
  /** The awareness layer's probes. Unknown or absent reads as false. */
  probes?: { screenSharing?: Probe; onCall?: Probe }
  /** The calendar layer's meeting flag (false until it exists). */
  inMeeting?: () => boolean
  /** A Live voice session is active (`() => isSessionActive(state.get().phase)`). */
  voiceSession?: () => boolean
  /** The dashboard is the window the worker is looking at. */
  dashboardFocused?: () => boolean
  /** The menu bar item (shellTray): gets the counts, and is refreshed when they change. Null when there is none (headless). */
  tray?: Pick<ShellTray, 'refresh' | 'setAttention'> | null
  /** understudy.chip: the two-second help-level glance asks first. */
  chip?: Pick<ChipDriver, 'setAttention'> | null
  /** The permission-prompt toast: takes the local lock only. */
  toast?: Pick<ToastHandle, 'setAttention'> | null
  /** understudy.proposals: reports to the layer instead of drawing its own toast. */
  proposals?: Pick<ProposalScheduler, 'setAttention' | 'noticeChoice'> | null
  /** The bridge's sources. Absent: the built-in loopback fetchers. `false`: no bridge at all. */
  sources?: ProducerSources | false
  /** Injected fetch for the built-in sources (default: the global fetch). */
  fetchImpl?: typeof fetch
  log?: (scope: string, ...args: unknown[]) => void
  now?: () => number
  // Tests and storyboards.
  env?: Record<string, string | undefined>
  force?: boolean
  client?: AttentionClient
  lock?: VoiceLock
  bridgeEveryMs?: number
}

export interface AttentionWiring {
  attention: AttentionHandle
  /** What Cue asks before it draws: pass it as `attention` to the Cue controller. */
  cuePort: CueAttentionPort
  /** The counts the menu bar shows. */
  badges(): TrayAttention
  /** The worker's signals right now (what the next poll will send). */
  signals(): AttentionSignals
  dispose(): void
}

/** Which dashboard page each action id opens. The adapter never builds a URL. `open_settings` goes to the Notices screen (how loudly it speaks):
 *  the dashboard has no settings screen, and an unknown route falls back to its home. */
export const ACTION_ROUTE: Readonly<Partial<Record<ActionId, DashboardRoute>>> = {
  open_queue: 'queue',
  open_routines: 'routines',
  open_briefing: 'today',
  open_summary: 'today',
  open_run: 'agents',
  open_report: 'agents',
  open_settings: 'notices',
  open_calendar: 'today',
  open_menu: 'today',
}

export const toHudNotice = (n: NoticeView): HudNotice => ({
  id: n.id,
  title: n.title,
  body: n.body,
  source: n.source,
  actions: n.actions.map((a) => ({ id: a.id, label: a.label })),
  urgent: n.priority >= 3,
})

const EMPTY: TrayAttention = { needsYou: 0, waiting: 0, marker: 'none' }
let current: AttentionWiring | null = null

export function wireAttention(deps: AttentionWiringDeps): AttentionWiring | null {
  if (!deps.force && !attentionEnabled(deps.env)) return null // off: no timer, no request, nothing bound
  if (current) return current
  const now = deps.now ?? Date.now
  const log = deps.log ?? (() => undefined)
  const safe = <T>(fn: () => T, fallback: T): T => {
    try {
      return fn()
    } catch {
      return fallback
    }
  }

  // ------------------------------------------------------------------ signals
  const flow = createFlowTracker({ now })
  const offInput = deps.inputTimes ? deps.inputTimes((t) => flow.onInput(Number.isFinite(t) ? t : undefined)) : null
  let lastFed = -Infinity
  const probes = { screen: false, call: false }
  let probesAt = -Infinity
  let probesBusy = false
  const readProbe = (p: Probe | undefined, set: (v: boolean) => void): Promise<void> | undefined => {
    if (!p) return undefined
    try {
      const v = p()
      if (v && typeof (v as Promise<unknown>).then === 'function') return (v as Promise<boolean | null | undefined>).then((x) => set(x === true), () => set(false))
      set(v === true)
    } catch {
      set(false)
    }
    return undefined
  }
  const refreshProbes = (t: number): void => {
    if (!deps.probes || probesBusy || t - probesAt < PROBE_EVERY_MS) return
    probesAt = t
    const pending = [readProbe(deps.probes.screenSharing, (v) => (probes.screen = v)), readProbe(deps.probes.onCall, (v) => (probes.call = v))].filter((p): p is Promise<void> => p !== undefined)
    if (pending.length === 0) return
    probesBusy = true
    void Promise.all(pending).finally(() => (probesBusy = false))
  }
  const quietNow = (until: number | null | undefined, t: number): boolean => until !== null && until !== undefined && until > t

  const signals = (): AttentionSignals => {
    const t = now()
    const bs = safe(() => deps.breakSignals?.() ?? null, null)
    const idleRaw = safe(() => (bs ? bs.idleSeconds() : deps.idleSeconds ? deps.idleSeconds() : null), null)
    const idle = typeof idleRaw === 'number' && Number.isFinite(idleRaw) ? Math.max(0, idleRaw) : null
    // No input feed: the system idle time says when the last input was, which is enough for a timestamp (never which key).
    if (!deps.inputTimes && idle !== null) {
      const lastInput = t - idle * 1000
      if (lastInput > lastFed + 500) {
        flow.onInput(lastInput)
        lastFed = lastInput
      }
    }
    const snap = flow.snapshot()
    refreshProbes(t)
    const task = safe(() => bs?.task() ?? null, null)
    const ended = safe(() => bs?.lastEpisodeEndAt() ?? null, null)
    const s = safe(() => deps.settings.get(), { cueQuietUntil: null, pausedUntil: null })
    const away = idle !== null && idle >= AWAY_AFTER_S
    return {
      typingBurst: snap.typingBurst,
      quietS: idle !== null ? Math.min(snap.quietS, idle) : snap.quietS,
      deepWork: snap.deepWork,
      taskInProgress: !!task && task.step < task.stepsTotal, // the same "unfinished task" the natural-break rules use
      taskMarkerS: ended === null ? null : Math.max(0, (t - ended) / 1000),
      away,
      awayS: away && idle !== null ? idle : 0,
      locked: safe(() => bs?.locked() === true, false),
      dnd: quietNow(s.cueQuietUntil, t) || quietNow(s.pausedUntil, t),
      screenSharing: probes.screen,
      onCall: probes.call,
      inMeeting: safe(() => deps.inMeeting?.() === true, false),
      voiceSession: safe(() => deps.voiceSession?.() === true, false),
      dashboardFocused: safe(() => deps.dashboardFocused?.() === true, false),
    }
  }

  // ------------------------------------------------------------------ ports
  let handle: AttentionHandle | null = null
  let badges: TrayAttention = EMPTY
  const ports: AttentionPorts = {
    showNotice(n) {
      if (n.channel === 'banner') {
        // A banner is a note on the dashboard (the engine's own words: "Nothing was shown on screen"): nothing is drawn, and the voice goes back
        // at once. Deferred one turn, because the adapter records the notice as current only after this call returns.
        queueMicrotask(() => handle?.adapter.closed(n.id, 'timeout'))
        return
      }
      safe(() => deps.hudModel.setNotice(toHudNotice(n)), undefined)
    },
    hideNotice(id) {
      safe(() => {
        if (deps.hudModel.state().notice?.id === id) deps.hudModel.setNotice(null)
      }, undefined)
    },
    setBadges(b: AttentionBadges) {
      const next: TrayAttention = { needsYou: b.needs_you, waiting: b.waiting, marker: b.marker }
      if (next.needsYou === badges.needsYou && next.waiting === badges.waiting && next.marker === badges.marker) return
      badges = next
      safe(() => deps.tray?.refresh(), undefined)
    },
    open(action) {
      const route = ACTION_ROUTE[action]
      if (route) safe(() => deps.openExternal(dashboardUrl(deps.endpoints, route)), undefined)
    },
  }

  // ------------------------------------------------------------------ start
  const sources = deps.sources === false ? undefined : (deps.sources ?? createSources({ ...deps, now, log }))
  const started = startAttention({
    engineUrl: deps.endpoints.engine,
    person: deps.person,
    signals,
    ports,
    killed: () => safe(() => deps.kill.isKilled(), false),
    sources,
    log,
    env: deps.env,
    client: deps.client,
    lock: deps.lock,
    force: deps.force,
    bridgeEveryMs: deps.bridgeEveryMs,
  })
  if (!started) return null
  const h: AttentionHandle = started
  handle = h

  // ------------------------------------------------------------------ the notice's buttons, from the HUD
  const sink: HudNoticeSink = {
    action(id, action) {
      // "Not now" and "Never for this" on a routine proposal also go to the engine's routine (when it is unambiguous which one it was).
      if ((action === 'not_now' || action === 'never') && h.adapter.current()?.id === id && h.adapter.current()?.type === 'routine_proposal') deps.proposals?.noticeChoice(action)
      h.adapter.action(id, action)
    },
    closed: (id, how) => h.adapter.closed(id, how),
  }
  deps.hudModel.setAttention(sink)

  // ------------------------------------------------------------------ producers and the optional hooks of the other files
  let wasKilled = safe(() => deps.kill.isKilled(), false)
  const offKill = deps.kill.subscribe((k) => {
    if (k.killed === wasKilled) return // the network leg of the same stop
    wasKilled = k.killed
    // Fire and forget, after the local stop has already happened: this layer never delays or gates the kill.
    void h.adapter.report({ type: k.killed ? 'kill_engaged' : 'kill_cleared', subject: 'kill' })
  })
  if (wasKilled) void h.adapter.report({ type: 'kill_engaged', subject: 'kill' })

  deps.chip?.setAttention({ admitGlance: (s) => h.adapter.admitGlance(s), releaseGlance: () => h.adapter.releaseGlance() })
  deps.toast?.setAttention({ lock: h.lock })
  deps.proposals?.setAttention({ report: (ev) => h.adapter.report(ev) })
  deps.tray?.setAttention(() => badges)

  let disposed = false
  const wiring: AttentionWiring = {
    attention: h,
    cuePort: h.adapter.cuePort(),
    badges: () => badges,
    signals,
    dispose() {
      if (disposed) return
      disposed = true
      offKill()
      offInput?.()
      h.stop() // hides the notice on the way out
      deps.hudModel.setAttention(null)
      deps.hudModel.setNotice(null)
      deps.chip?.setAttention(null)
      deps.toast?.setAttention(null)
      deps.proposals?.setAttention(null)
      badges = EMPTY
      deps.tray?.setAttention(null)
      current = null
    },
  }
  current = wiring
  return wiring
}

// ---------------------------------------------------------------------------------------------------------------------------------------
// The producer bridge's sources: what the shell can already read, as ids and enums. Loopback only, a short timeout, read-only (GET), and any
// failure answers null (the bridge then raises and resolves nothing on that read).
type SourceDeps = Pick<AttentionWiringDeps, 'endpoints' | 'person' | 'fetchImpl' | 'proposals'> & { now: () => number; log: (scope: string, ...args: unknown[]) => void }

const asRecord = (v: unknown): Record<string, unknown> | null => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null)
const asList = (v: unknown): unknown[] | null => (Array.isArray(v) ? v : Array.isArray(asRecord(v)?.data) ? (asRecord(v)?.data as unknown[]) : null)
const str = (v: unknown): string | null => (typeof v === 'string' && v.length > 0 ? v : null)
const day = (t: number): string => {
  const d = new Date(t)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function createSources(d: SourceDeps): ProducerSources {
  const timeoutMs = 1_500
  /** One GET to a loopback URL. The Response, or null on anything other than a 2xx. */
  async function get(url: string): Promise<Response | null> {
    if (!isLoopbackUrl(url)) return null
    const ctl = new AbortController()
    const timer = setTimeout(() => ctl.abort(), timeoutMs)
    try {
      const res = await (d.fetchImpl ?? fetch)(url, { method: 'GET', signal: ctl.signal, headers: { 'X-Understudy-Actor': 'desktop' } })
      return res.ok ? res : null
    } catch {
      return null
    } finally {
      clearTimeout(timer)
    }
  }
  const json = async (url: string): Promise<unknown | null> => {
    const res = await get(url)
    if (!res) return null
    try {
      return await res.json()
    } catch {
      return null
    }
  }
  const engine = d.endpoints.engine.replace(/\/+$/, '')
  const agent = d.endpoints.agent.replace(/\/+$/, '')
  const startedAt = d.now()

  /** A source read at most every `ms`: in between it answers what it last read. A failed read is not remembered, so it is tried again next time. */
  const every = <T>(ms: number, read: () => Promise<T | null>): (() => Promise<T | null>) => {
    let at = -Infinity
    let last: T | null = null
    return async () => {
      const t = d.now()
      if (last !== null && t - at < ms) return last
      const v = await read()
      if (v !== null) {
        last = v
        at = t
      }
      return v
    }
  }

  // The run list, remembered so an approval can say whether a live run is waiting for it.
  let liveRuns = new Set<string>()
  const seenRunning = new Set<string>()

  const runMode = (m: unknown): RunView['mode'] => (m === 'nightly' || m === 'overnight' ? 'overnight' : m === 'background' ? 'background' : 'foreground')
  const runState = (s: unknown): RunView['state'] | null => {
    if (s === 'done' || s === 'failed' || s === 'paused' || s === 'yielded' || s === 'stopped') return s
    if (s === 'timeout') return 'failed'
    return null // created, planning, running...: still going
  }

  const approvals = async (): Promise<QueueItemView[] | null> => {
    const list = asList(await json(`${engine}/queue?status=pending`))
    if (!list) return null
    const out: QueueItemView[] = []
    for (const raw of list) {
      const r = asRecord(raw)
      const id = r && str(r.id)
      if (!r || !id) continue
      const kind = ['irreversible_step', 'outward_step', 'batch_result', 'injection_pause', 'shadow_mismatch'].includes(String(r.kind)) ? (r.kind as QueueItemView['kind']) : 'batch_result'
      const risk = r.risk_class === 'irreversible' || r.risk_class === 'outward' ? r.risk_class : 'normal'
      const runId = str(r.run_id)
      out.push({ id, kind, risk, runId, blocksRun: runId !== null && liveRuns.has(runId) })
    }
    return out
  }

  const runs = async (): Promise<RunView[] | null> => {
    const person = d.person()
    const list = asList(await json(`${agent}/agents/runs${person ? `?person=${encodeURIComponent(person)}` : ''}`))
    if (!list) return null
    const out: RunView[] = []
    const live = new Set<string>()
    for (const raw of list.slice(0, 40)) {
      const r = asRecord(raw)
      const id = r && str(r.run_id)
      if (!r || !id) continue
      const state = runState(r.state)
      const startedMs = Date.parse(String(r.started ?? ''))
      if (state === null || state === 'paused') {
        live.add(id)
        seenRunning.add(id)
      }
      if (state === null) continue
      // Runs that ended before the app started are history, not news: only those started since, or seen running, are reported.
      if (state !== 'paused' && !(Number.isFinite(startedMs) && startedMs >= startedAt - 60_000) && !seenRunning.has(id)) continue
      // The run list does not say why a run paused, so a paused run is not turned into a "needs you" event here.
      out.push({ id, mode: runMode(r.mode), state, needsHuman: null })
    }
    liveRuns = live
    return out
  }

  const briefing = every(300_000, async () => {
    const person = d.person()
    if (!person) return null
    const body = asRecord(await json(`${engine}/briefing?person=${encodeURIComponent(person)}`))
    const data = asRecord(body?.data)
    const cards = Array.isArray(data?.cards) ? (data?.cards as unknown[]).length : null
    return data && cards !== null ? { generation: String(data.generated_at ?? day(d.now())), cards } : null
  })

  const morning = every(300_000, async () => {
    const t = d.now()
    const since = new Date(new Date(t).setHours(0, 0, 0, 0) - 6 * 3_600_000).toISOString() // last evening onwards: the overnight runs
    const body = asRecord(await json(`${agent}/agents/morning?since=${encodeURIComponent(since)}`))
    return body && Array.isArray(body.runs) ? { id: day(t), runs: body.runs.length } : null
  })

  const proposals = async (): Promise<Array<{ id: string }> | null> => {
    const list = asList(await json(`${engine}/routines`))
    if (!list) return null
    return list.flatMap((raw) => {
      const r = asRecord(raw)
      const id = r && str(r.id)
      return r && id && r.status === 'proposed' ? [{ id }] : []
    })
  }

  // A service is reported as degraded only once it has answered and then failed twice running: an agent service the worker never started is
  // not "degraded", and one slow answer is not an outage.
  const everUp = new Set<string>()
  const fails = new Map<string, number>()
  const services = async (): Promise<Array<{ service: 'engine' | 'agent'; ok: boolean }>> => {
    const out: Array<{ service: 'engine' | 'agent'; ok: boolean }> = []
    for (const [service, base] of [['engine', engine], ['agent', agent]] as const) {
      const ok = (await get(`${base}/health`)) !== null
      if (ok) {
        everUp.add(service)
        fails.set(service, 0)
      } else fails.set(service, (fails.get(service) ?? 0) + 1)
      if (everUp.has(service)) out.push({ service, ok: ok || (fails.get(service) ?? 0) < 2 })
    }
    return out
  }

  return {
    approvals,
    runs,
    briefing,
    morning,
    services,
    // The proposals scheduler reports routines itself when it is bound to the layer; polling them here too would raise each one twice.
    ...(d.proposals ? {} : { proposals }),
  }
}
