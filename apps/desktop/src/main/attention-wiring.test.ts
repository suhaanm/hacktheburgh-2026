// The attention layer wired into the shell (attention-wiring.ts): hermetic. A fake clock, a fake engine client, fake ports and a fake fetch; every
// URL here is on an unused loopback port (the desktop test setup refuses the live dev ports). Nothing real is touched.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { HudState } from '../shared/hud'
import { ACTION_ROUTE, AWAY_AFTER_S, createSources, toHudNotice, wireAttention, type AttentionWiring, type AttentionWiringDeps } from './attention-wiring'
import { createFakeClient } from './attention/client'
import type { NoticeView } from './attention/adapter'
import { ACTION_IDS, parseNext, type AttentionItem } from './attention/types'
import { dashboardUrl } from './engine/endpoints'
import { createHudModel } from './hud-model'
import type { KillState } from './kill-switch'

const ENDPOINTS = { engine: 'http://127.0.0.1:18700', agent: 'http://127.0.0.1:18710', dashboard: 'http://127.0.0.1:18173' }

const item = (over: Partial<AttentionItem> = {}): AttentionItem => ({
  id: 'i_one', type: 'approval_blocking', channel: 'toast', text_id: 'approval_blocking', title: 'An approval is waiting', body: 'Approval queue: 1 approval waiting.',
  source: 'Approval queue', count: 1, actions: [{ id: 'open_queue', label: 'Open the queue' }, { id: 'dismiss', label: 'Close' }], priority: 2, new: true, preempt: false,
  reminder: false, display_s: 20, expires_in_s: 100, reason_code: 'shown_break', ...over,
})
const next = (it: AttentionItem | null, needs = 0, marker: 'none' | 'needs_you' | 'stopped' = needs ? 'needs_you' : 'none') =>
  parseNext({ data: { item: it, active: null, badges: { needs_you: needs, waiting: 0, marker, stopped: marker === 'stopped' }, digest_ready: false, poll_after_s: 2 } })

function fakeKill(initial = false) {
  let state: KillState = { killed: initial, at: null, source: null, engine: null, agent: null }
  const listeners = new Set<(s: KillState) => void>()
  return {
    api: {
      trigger: vi.fn(async () => ({ source: 'hud' as const, at: 1, localMs: 1, engine: true, agent: true })),
      clear: vi.fn(async () => undefined),
      isKilled: () => state.killed,
      state: () => state,
      subscribe: (cb: (s: KillState) => void) => (listeners.add(cb), () => void listeners.delete(cb)),
    },
    set(patch: Partial<KillState>) {
      state = { ...state, ...patch }
      for (const l of [...listeners]) l(state)
    },
    listeners,
  }
}

function rig(over: Partial<AttentionWiringDeps> & { script?: Parameters<typeof createFakeClient>[0]; killed?: boolean } = {}) {
  const fake = createFakeClient(over.script ?? {})
  const kill = fakeKill(over.killed ?? false)
  const pushed: HudState[] = []
  const opened: string[] = []
  const sinkOpened: string[] = []
  const hud = createHudModel({
    kill: kill.api,
    endpoints: { dashboard: ENDPOINTS.dashboard },
    openExternal: (u) => void sinkOpened.push(u),
    onProposalChoice: () => undefined,
    push: (s) => void pushed.push(s),
  })
  const settings = { cueQuietUntil: null as number | null, pausedUntil: null as number | null }
  const tray = { refresh: vi.fn(), setAttention: vi.fn() }
  const chip = { setAttention: vi.fn() }
  const toast = { setAttention: vi.fn() }
  const proposals = { setAttention: vi.fn(), noticeChoice: vi.fn(() => true) }
  const wiring = wireAttention({
    endpoints: ENDPOINTS,
    person: () => 'p_test',
    settings: { get: () => settings },
    hudModel: hud,
    openExternal: (u) => void opened.push(u),
    kill: kill.api,
    tray,
    chip,
    toast,
    proposals,
    sources: false,
    force: true,
    client: fake.client,
    ...over,
  }) as AttentionWiring
  return { wiring, fake, kill, hud, pushed, opened, sinkOpened, settings, tray, chip, toast, proposals }
}

let live: AttentionWiring | null = null
beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-11-07T10:00:00'))
})
afterEach(() => {
  live?.dispose()
  live = null
  vi.useRealTimers()
})
const up = (r: ReturnType<typeof rig>) => (live = r.wiring)
const flush = () => vi.advanceTimersByTimeAsync(0)

describe('off by default', () => {
  it('returns null when the flag is off, creates no timer, makes no request and binds nothing', () => {
    const fetchImpl = vi.fn()
    const hudModel = { setNotice: vi.fn(), setAttention: vi.fn(), state: () => ({ notice: null }) as unknown as HudState }
    const tray = { refresh: vi.fn(), setAttention: vi.fn() }
    const chip = { setAttention: vi.fn() }
    const kill = fakeKill()
    const w = wireAttention({ endpoints: ENDPOINTS, person: () => 'p_test', settings: { get: () => ({ cueQuietUntil: null, pausedUntil: null }) }, hudModel, openExternal: vi.fn(), kill: kill.api, tray, chip, fetchImpl: fetchImpl as unknown as typeof fetch, env: {} })
    expect(w).toBeNull()
    expect(vi.getTimerCount()).toBe(0)
    expect(fetchImpl).not.toHaveBeenCalled()
    expect(hudModel.setAttention).not.toHaveBeenCalled()
    expect(tray.setAttention).not.toHaveBeenCalled()
    expect(chip.setAttention).not.toHaveBeenCalled()
    expect(kill.listeners.size).toBe(0)
  })

  it('the master flag UNDERSTUDY_X=1 or UNDERSTUDY_X_ATTENTION=1 turns it on (no force needed)', () => {
    for (const env of [{ UNDERSTUDY_X: '1' }, { UNDERSTUDY_X_ATTENTION: '1' }]) {
      const r = rig({ force: false, env })
      expect(r.wiring).not.toBeNull()
      r.wiring.dispose()
    }
  })

  it('a second call while it runs answers the same wiring, and dispose frees the slot', () => {
    const r = rig()
    up(r)
    expect(wireAttention({ endpoints: ENDPOINTS, person: () => 'p_test', settings: { get: () => r.settings }, hudModel: r.hud, openExternal: vi.fn(), kill: r.kill.api, force: true, client: r.fake.client, sources: false })).toBe(r.wiring)
    r.wiring.dispose()
    live = null
    const again = rig()
    expect(again.wiring).not.toBe(r.wiring)
    live = again.wiring
  })
})

describe('signals', () => {
  it('feeds the flow tracker with timestamps only: a typing burst, then quiet seconds, then deep work', () => {
    let feed: ((t: number) => void) | null = null
    const off = vi.fn()
    const r = rig({ inputTimes: (cb) => ((feed = cb), off) })
    up(r)
    const t0 = Date.now()
    feed!(t0 - 1500)
    feed!(t0 - 1000)
    feed!(t0 - 500)
    const burst = r.wiring.signals()
    expect(burst.typingBurst).toBe(true)
    expect(burst.quietS).toBeCloseTo(0.5, 1)
    vi.advanceTimersByTime(4_000)
    const quiet = r.wiring.signals()
    expect(quiet.typingBurst).toBe(false)
    expect(quiet.quietS).toBeCloseTo(4.5, 1)
    for (let i = 0; i < 27; i++) {
      vi.advanceTimersByTime(60_000)
      feed!(Date.now())
    }
    expect(r.wiring.signals().deepWork).toBe(true)
    r.wiring.dispose()
    live = null
    expect(off).toHaveBeenCalledTimes(1)
  })

  it('a bad timestamp is not a crash', () => {
    let feed: ((t: number) => void) | null = null
    const r = rig({ inputTimes: (cb) => ((feed = cb), () => undefined) })
    up(r)
    expect(() => feed!(Number.NaN)).not.toThrow()
    expect(r.wiring.signals().quietS).toBeGreaterThanOrEqual(0)
  })

  it('without an input feed, the system idle time stands in for the last input', () => {
    let idle = 0.4
    const r = rig({ idleSeconds: () => idle })
    up(r)
    expect(r.wiring.signals().quietS).toBeCloseTo(0.4, 1)
    idle = 100
    vi.advanceTimersByTime(100_000)
    expect(r.wiring.signals().quietS).toBeCloseTo(100, 0)
  })

  it('presence, the screen lock and the task come from the break signals', () => {
    let idle = 10
    let locked = false
    let task: { step: number; stepsTotal: number } | null = null
    let ended: number | null = null
    const r = rig({ breakSignals: () => ({ idleSeconds: () => idle, locked: () => locked, task: () => task, lastEpisodeEndAt: () => ended }) })
    up(r)
    expect(r.wiring.signals()).toMatchObject({ away: false, awayS: 0, locked: false, taskInProgress: false, taskMarkerS: null })
    idle = AWAY_AFTER_S + 60
    locked = true
    task = { step: 2, stepsTotal: 5 }
    ended = Date.now() - 30_000
    expect(r.wiring.signals()).toMatchObject({ away: true, awayS: AWAY_AFTER_S + 60, locked: true, taskInProgress: true, taskMarkerS: 30 })
    task = { step: 5, stepsTotal: 5 } // the last step: the same "unfinished" rule as the natural-break check
    expect(r.wiring.signals().taskInProgress).toBe(false)
  })

  it('dnd is Cue quiet-until or the menu pause-until, while in the future', () => {
    const r = rig()
    up(r)
    expect(r.wiring.signals().dnd).toBe(false)
    r.settings.cueQuietUntil = Date.now() + 60_000
    expect(r.wiring.signals().dnd).toBe(true)
    r.settings.cueQuietUntil = Date.now() - 1
    expect(r.wiring.signals().dnd).toBe(false)
    r.settings.pausedUntil = Date.now() + 60_000
    expect(r.wiring.signals().dnd).toBe(true)
    r.settings.pausedUntil = null
    expect(r.wiring.signals().dnd).toBe(false)
  })

  it('screen sharing and a call come from the probes, and unknown is false', async () => {
    const none = rig()
    up(none)
    expect(none.wiring.signals()).toMatchObject({ screenSharing: false, onCall: false, inMeeting: false, voiceSession: false, dashboardFocused: false })
    none.wiring.dispose()
    live = null

    const sync = rig({ probes: { screenSharing: () => true, onCall: () => null } })
    up(sync)
    expect(sync.wiring.signals()).toMatchObject({ screenSharing: true, onCall: false })
    sync.wiring.dispose()
    live = null

    const slow = rig({ probes: { screenSharing: async () => true, onCall: async () => { throw new Error('probe broke') } } })
    up(slow)
    expect(slow.wiring.signals().screenSharing).toBe(false) // not read yet: unknown
    await flush()
    expect(slow.wiring.signals()).toMatchObject({ screenSharing: true, onCall: false })
  })

  it('meeting, voice session and dashboard focus come from the getters, and a getter that throws is false', () => {
    const r = rig({ inMeeting: () => true, voiceSession: () => true, dashboardFocused: () => { throw new Error('no window') } })
    up(r)
    expect(r.wiring.signals()).toMatchObject({ inMeeting: true, voiceSession: true, dashboardFocused: false })
  })
})

describe('ports: a notice on the HUD, and its buttons back', () => {
  it('draws the engine\'s words on the HUD and removes them when the display time is over', async () => {
    const r = rig({ script: { next: [next(item(), 1)] } })
    up(r)
    await flush()
    expect(r.hud.state().notice).toEqual({ id: 'i_one', title: 'An approval is waiting', body: 'Approval queue: 1 approval waiting.', source: 'Approval queue', actions: [{ id: 'open_queue', label: 'Open the queue' }, { id: 'dismiss', label: 'Close' }], urgent: false })
    await vi.advanceTimersByTimeAsync(20_001)
    expect(r.hud.state().notice).toBeNull()
    expect(r.wiring.attention.lock.holder()).toBeNull()
    expect(r.fake.calls.feedback).toEqual([]) // untouched: the engine labels it by itself
  })

  it('a safety item is announced as urgent', () => {
    const n: NoticeView = { id: 'i_s', type: 'injection_pause', title: 'A run paused', body: 'Your agent run paused.', source: 'Your agent run', channel: 'toast', actions: [], displayMs: 1000, priority: 3, reminder: false, preempt: true }
    expect(toHudNotice(n).urgent).toBe(true)
    expect(toHudNotice({ ...n, priority: 1 }).urgent).toBe(false)
  })

  it('a button goes to the adapter: it opens the dashboard page, reports followed, and the card goes', async () => {
    const r = rig({ script: { next: [next(item(), 1)] } })
    up(r)
    await flush()
    vi.advanceTimersByTime(3_000)
    expect(r.hud.handle({ type: 'notice', id: 'i_one', action: 'open_queue' })).toBe(true)
    expect(r.opened).toEqual([`${ENDPOINTS.dashboard}/#/queue`])
    expect(r.sinkOpened).toEqual([]) // the wiring opens it, not the HUD's own opener
    expect(r.fake.calls.feedback).toEqual([{ itemId: 'i_one', event: 'followed', seconds: 3 }])
    expect(r.hud.state().notice).toBeNull()
    expect(r.wiring.attention.lock.holder()).toBeNull()
  })

  it('closing without a button (Escape) reports dismissed once; a stale click or a bad action does nothing', async () => {
    const r = rig({ script: { next: [next(item(), 1)] } })
    up(r)
    await flush()
    expect(r.hud.handle({ type: 'notice', id: 'i_other', action: 'open_queue' })).toBe(false)
    expect(r.hud.handle({ type: 'notice', id: 'i_one', action: 'open_anything' })).toBe(false)
    expect(r.hud.handle({ type: 'notice_closed', id: 'i_one', how: 'sulked' })).toBe(false)
    expect(r.hud.state().notice?.id).toBe('i_one')
    expect(r.hud.handle({ type: 'notice_closed', id: 'i_one', how: 'dismissed' })).toBe(true)
    expect(r.fake.calls.feedback).toEqual([{ itemId: 'i_one', event: 'dismissed', seconds: 0 }])
    expect(r.hud.state().notice).toBeNull()
    expect(r.hud.handle({ type: 'notice_closed', id: 'i_one', how: 'dismissed' })).toBe(false)
    expect(r.fake.calls.feedback).toHaveLength(1)
    expect(r.wiring.attention.lock.holder()).toBeNull()
  })

  it('a banner is a note for the dashboard: nothing is drawn and the voice goes straight back', async () => {
    const r = rig({ script: { next: [next(item({ id: 'i_b', channel: 'banner' }), 0)] } })
    up(r)
    await flush()
    expect(r.hud.state().notice).toBeNull()
    expect(r.wiring.attention.adapter.current()).toBeNull()
    expect(r.wiring.attention.lock.holder()).toBeNull()
  })

  it('every action id that opens a page has a dashboard route, and the URL is the dashboard\'s', () => {
    const e = { dashboard: ENDPOINTS.dashboard }
    expect(dashboardUrl(e, 'queue')).toBe(`${ENDPOINTS.dashboard}/#/queue`)
    expect(dashboardUrl(e, 'routines')).toBe(`${ENDPOINTS.dashboard}/#/routines`)
    expect(dashboardUrl(e, 'today')).toBe(`${ENDPOINTS.dashboard}/#/today`)
    expect(dashboardUrl(e, 'agents')).toBe(`${ENDPOINTS.dashboard}/#/agents`)
    expect(dashboardUrl(e, 'notices')).toBe(`${ENDPOINTS.dashboard}/#/notices`)
    expect(ACTION_ROUTE).toMatchObject({ open_queue: 'queue', open_routines: 'routines', open_briefing: 'today', open_summary: 'today', open_run: 'agents', open_report: 'agents' })
    for (const a of ACTION_IDS) if (a.startsWith('open_')) expect(ACTION_ROUTE[a], a).toBeDefined()
    for (const a of ['dismiss', 'not_now', 'never'] as const) expect(ACTION_ROUTE[a]).toBeUndefined()
  })

  it('opening a report goes to the agents page', async () => {
    const r = rig({ script: { next: [next(item({ id: 'i_r', type: 'run_finished', actions: [{ id: 'open_report', label: 'Open the report' }, { id: 'dismiss', label: 'Close' }] }), 0)] } })
    up(r)
    await flush()
    r.hud.handle({ type: 'notice', id: 'i_r', action: 'open_report' })
    expect(r.opened).toEqual([`${ENDPOINTS.dashboard}/#/agents`])
  })

  it('the counts go to the menu bar, which is refreshed only when they change', async () => {
    const r = rig({ script: { next: [next(null, 2)] } })
    up(r)
    await flush()
    expect(r.tray.setAttention).toHaveBeenCalledTimes(1)
    const source = r.tray.setAttention.mock.calls[0][0] as () => unknown
    expect(source()).toEqual({ needsYou: 2, waiting: 0, marker: 'needs_you' })
    expect(r.tray.refresh).toHaveBeenCalledTimes(1)
    r.fake.push(next(null, 2))
    await r.wiring.attention.adapter.pollOnce()
    expect(r.tray.refresh).toHaveBeenCalledTimes(1)
    r.fake.push(next(null, 0))
    await r.wiring.attention.adapter.pollOnce()
    expect(r.tray.refresh).toHaveBeenCalledTimes(2)
    expect(source()).toEqual({ needsYou: 0, waiting: 0, marker: 'none' })
    expect(r.wiring.badges()).toEqual({ needsYou: 0, waiting: 0, marker: 'none' })
  })

  it('the stopped marker is passed on as it is: the kill state itself is never delayed by this layer', async () => {
    const r = rig({ script: { next: [next(null, 0, 'stopped')] } })
    up(r)
    await flush()
    expect(r.wiring.badges().marker).toBe('stopped')
  })
})

describe('producers', () => {
  it('the kill switch: engaging reports kill_engaged once, the network leg does not repeat it, clearing reports kill_cleared', () => {
    const r = rig()
    up(r)
    r.kill.set({ killed: true, source: 'hud' })
    expect(r.fake.calls.submit).toHaveLength(1)
    expect(r.fake.calls.submit[0]).toMatchObject({ type: 'kill_engaged', subject: 'kill' })
    r.kill.set({ engine: true, agent: false }) // the engine and agent leg of the same stop
    expect(r.fake.calls.submit).toHaveLength(1)
    r.kill.set({ killed: false })
    expect(r.fake.calls.submit).toHaveLength(2)
    expect(r.fake.calls.submit[1]).toMatchObject({ type: 'kill_cleared', subject: 'kill' })
  })

  it('a kill already on when it starts is reported', () => {
    const r = rig({ killed: true })
    up(r)
    expect(r.fake.calls.submit).toHaveLength(1)
    expect(r.fake.calls.submit[0]).toMatchObject({ type: 'kill_engaged', subject: 'kill' })
  })

  it('an engine that never answers does not hold up the kill switch: the listener returns at once and nothing is awaited', () => {
    const r = rig({ script: { submit: () => new Promise(() => undefined) as never } })
    up(r)
    let returned = false
    r.kill.set({ killed: true })
    returned = true
    expect(returned).toBe(true)
    expect(r.kill.api.isKilled()).toBe(true)
    expect(r.fake.calls.submit[0]).toMatchObject({ type: 'kill_engaged' })
  })

  it('the help-level glance asks the layer and gives the voice back', async () => {
    const r = rig()
    up(r)
    const port = r.chip.setAttention.mock.calls[0][0] as { admitGlance(s: string): Promise<boolean>; releaseGlance(): void }
    expect(await port.admitGlance('lv_2')).toBe(true)
    expect(r.fake.calls.submit.at(-1)).toMatchObject({ type: 'help_level_changed', subject: 'lv_2' })
    expect(r.wiring.attention.lock.holder()?.owner).toBe('glance')
    port.releaseGlance()
    expect(r.wiring.attention.lock.holder()).toBeNull()
  })

  it('a refused glance is false and leaves the voice free', async () => {
    const r = rig({ script: { submit: () => ({ itemId: null, show: false, reason: 'quiet_flow', coalesced: false }) } })
    up(r)
    const port = r.chip.setAttention.mock.calls[0][0] as { admitGlance(s: string): Promise<boolean> }
    expect(await port.admitGlance('lv_3')).toBe(false)
    expect(r.wiring.attention.lock.holder()).toBeNull()
  })

  it('the permission-prompt toast gets the layer\'s own lock (and nothing else)', () => {
    const r = rig()
    up(r)
    expect(r.toast.setAttention).toHaveBeenCalledTimes(1)
    expect(r.toast.setAttention.mock.calls[0][0]).toEqual({ lock: r.wiring.attention.lock })
  })

  it('a proposal is reported through the layer, with the routine id as the subject', async () => {
    const r = rig()
    up(r)
    const port = r.proposals.setAttention.mock.calls[0][0] as { report(ev: { type: string; subject: string; op?: string }): Promise<void> }
    await port.report({ type: 'routine_proposal', subject: 'calc-entry-3x' } as never)
    await port.report({ type: 'routine_proposal', subject: 'calc-entry-3x', op: 'resolve' } as never)
    expect(r.fake.calls.submit.map((e) => [e.type, e.subject, e.op])).toEqual([
      ['routine_proposal', 'calc-entry-3x', undefined],
      ['routine_proposal', 'calc-entry-3x', 'resolve'],
    ])
  })

  it('Not now and Never for this on a routine notice also reach the routine (before the layer clears it); other notices never do', async () => {
    const proposal = item({ id: 'i_rp', type: 'routine_proposal', actions: [{ id: 'open_routines', label: 'Look at it' }, { id: 'not_now', label: 'Not now' }, { id: 'never', label: 'Never for this' }] })
    const r = rig({ script: { next: [next(proposal, 1)] } })
    up(r)
    await flush()
    expect(r.hud.handle({ type: 'notice', id: 'i_rp', action: 'not_now' })).toBe(true)
    expect(r.proposals.noticeChoice).toHaveBeenCalledTimes(1)
    expect(r.proposals.noticeChoice).toHaveBeenCalledWith('not_now')
    expect(r.fake.calls.feedback.at(-1)).toMatchObject({ itemId: 'i_rp', event: 'dismissed' })

    r.fake.push(next(proposal, 1))
    await r.wiring.attention.adapter.pollOnce()
    expect(r.hud.handle({ type: 'notice', id: 'i_rp', action: 'never' })).toBe(true)
    expect(r.proposals.noticeChoice).toHaveBeenLastCalledWith('never')
    expect(r.fake.calls.feedback.at(-1)).toMatchObject({ itemId: 'i_rp', event: 'never' })

    r.fake.push(next(item({ id: 'i_q', actions: [{ id: 'dismiss', label: 'Close' }] }), 1))
    await r.wiring.attention.adapter.pollOnce()
    r.hud.handle({ type: 'notice', id: 'i_q', action: 'dismiss' })
    expect(r.proposals.noticeChoice).toHaveBeenCalledTimes(2)
  })

  it('open_routines on the routine notice does not decline anything', async () => {
    const proposal = item({ id: 'i_rp', type: 'routine_proposal', actions: [{ id: 'open_routines', label: 'Look at it' }, { id: 'not_now', label: 'Not now' }] })
    const r = rig({ script: { next: [next(proposal, 1)] } })
    up(r)
    await flush()
    r.hud.handle({ type: 'notice', id: 'i_rp', action: 'open_routines' })
    expect(r.proposals.noticeChoice).not.toHaveBeenCalled()
    expect(r.opened).toEqual([`${ENDPOINTS.dashboard}/#/routines`])
  })

  it('the bridge sources reach the engine as events (an approval raised once)', async () => {
    const sources = { approvals: async () => [{ id: 'q_9', kind: 'batch_result' as const, risk: 'normal' as const, blocksRun: false }] }
    const r = rig({ sources })
    up(r)
    await flush()
    expect(r.fake.calls.submit).toHaveLength(1)
    expect(r.fake.calls.submit[0]).toMatchObject({ type: 'approval_waiting', subject: 'q_9' })
    expect(vi.getTimerCount()).toBeGreaterThan(0) // the layer's own poll and the bridge's, both fake here
  })
})

describe('dispose', () => {
  it('unbinds every hook, removes the notice and leaves no timer or listener behind', async () => {
    let feed: ((t: number) => void) | null = null
    const offInput = vi.fn()
    const r = rig({ script: { next: [next(item(), 1)] }, inputTimes: (cb) => ((feed = cb), offInput) })
    await flush()
    expect(r.hud.state().notice).not.toBeNull()
    expect(feed).not.toBeNull()
    r.wiring.dispose()
    r.wiring.dispose() // idempotent
    expect(r.hud.state().notice).toBeNull()
    expect(r.hud.handle({ type: 'notice', id: 'i_one', action: 'open_queue' })).toBe(false)
    expect(r.chip.setAttention).toHaveBeenLastCalledWith(null)
    expect(r.toast.setAttention).toHaveBeenLastCalledWith(null)
    expect(r.proposals.setAttention).toHaveBeenLastCalledWith(null)
    expect(r.tray.setAttention).toHaveBeenLastCalledWith(null)
    expect(offInput).toHaveBeenCalledTimes(1)
    expect(r.kill.listeners.size).toBe(1) // only the HUD model's own subscription is left
    expect(vi.getTimerCount()).toBe(0)
    r.kill.set({ killed: true })
    expect(r.fake.calls.submit).toEqual([])
  })
})

// ---------------------------------------------------------------------------------------------------------------------------------------
describe('producer sources (read-only loopback fetchers)', () => {
  type Reply = { ok?: boolean; json?: unknown; text?: boolean }
  function fakeFetch(routes: Record<string, Reply | (() => Reply)>) {
    const calls: Array<{ url: string; method?: string; actor?: string }> = []
    const impl = (async (url: string, init?: RequestInit) => {
      calls.push({ url, method: init?.method, actor: (init?.headers as Record<string, string> | undefined)?.['X-Understudy-Actor'] })
      const key = Object.keys(routes).find((k) => url.startsWith(k))
      if (!key) throw new Error('connection refused')
      const r = typeof routes[key] === 'function' ? (routes[key] as () => Reply)() : (routes[key] as Reply)
      return { ok: r.ok ?? true, status: r.ok === false ? 500 : 200, json: async () => { if (r.text) throw new SyntaxError('not json'); return r.json } }
    }) as unknown as typeof fetch
    return { impl, calls }
  }
  const make = (routes: Record<string, Reply | (() => Reply)>, over: Partial<Parameters<typeof createSources>[0]> = {}) => {
    const f = fakeFetch(routes)
    let t = Date.now()
    const sources = createSources({ endpoints: ENDPOINTS, person: () => 'p_test', fetchImpl: f.impl, now: () => t, log: () => undefined, ...over })
    return { sources, f, tick: (ms: number) => void (t += ms) }
  }

  it('approvals: ids and enums only, kinds the queue does not know become a plain batch result, and a live run makes it blocking', async () => {
    const { sources, f } = make({
      [`${ENDPOINTS.engine}/queue?status=pending`]: { json: { data: [
        { id: 'q_1', kind: 'irreversible_step', risk_class: 'irreversible', run_id: 'run_7', title: 'should never be read' },
        { id: 'q_2', kind: 'outward_step', risk_class: 'outward', run_id: 'run_8' },
        { id: 'q_3', kind: 'something_new', risk_class: 'weird' },
        { kind: 'batch_result' }, // no id
      ] } },
      [`${ENDPOINTS.agent}/agents/runs`]: { json: [{ run_id: 'run_8', state: 'running', mode: 'background', started: new Date().toISOString() }] },
    })
    await sources.runs!() // learns that run_8 is live
    const items = await sources.approvals!()
    expect(items).toEqual([
      { id: 'q_1', kind: 'irreversible_step', risk: 'irreversible', runId: 'run_7', blocksRun: false },
      { id: 'q_2', kind: 'outward_step', risk: 'outward', runId: 'run_8', blocksRun: true },
      { id: 'q_3', kind: 'batch_result', risk: 'normal', runId: null, blocksRun: false },
    ])
    expect(f.calls.every((c) => c.method === 'GET' && c.actor === 'desktop')).toBe(true)
  })

  it('a browser task waiting for its one click is a known kind and always blocks that task', async () => {
    const { sources } = make({
      [`${ENDPOINTS.engine}/queue?status=pending`]: { json: { data: [{ id: 'q_5', kind: 'browser_step', risk_class: 'normal', run_id: 'tk_0a0b0c0d', title: 'Click on example.org' }] } },
    })
    expect(await sources.approvals!()).toEqual([{ id: 'q_5', kind: 'browser_step', risk: 'normal', runId: 'tk_0a0b0c0d', blocksRun: true }])
  })

  it('answers null on any failure: an error status, a bad body, a refused connection, a timeout, or a host that is not this machine', async () => {
    expect(await make({ [`${ENDPOINTS.engine}/queue`]: { ok: false } }).sources.approvals!()).toBeNull()
    expect(await make({ [`${ENDPOINTS.engine}/queue`]: { text: true } }).sources.approvals!()).toBeNull()
    expect(await make({ [`${ENDPOINTS.engine}/queue`]: { json: { not: 'a list' } } }).sources.approvals!()).toBeNull()
    expect(await make({}).sources.approvals!()).toBeNull()
    const remote = make({ 'http://example.com:18700/queue': { json: [] } }, { endpoints: { ...ENDPOINTS, engine: 'http://example.com:18700' } })
    expect(await remote.sources.approvals!()).toBeNull()
    expect(remote.f.calls).toEqual([]) // never sent

    const hang = (async (_url: string, init?: RequestInit) => new Promise((_, reject) => init?.signal?.addEventListener('abort', () => reject(new Error('aborted'))))) as unknown as typeof fetch
    const s = createSources({ endpoints: ENDPOINTS, person: () => 'p_test', fetchImpl: hang, now: Date.now, log: () => undefined })
    const pending = s.approvals!()
    await vi.advanceTimersByTimeAsync(1_600)
    expect(await pending).toBeNull()
  })

  it('runs: only runs that started since this app did, or that were seen running, are reported; modes and states are mapped', async () => {
    let list: unknown[] = [
      { run_id: 'r_old', state: 'done', mode: 'nightly', started: '2020-01-01T00:00:00Z' },
      { run_id: 'r_new', state: 'failed', mode: 'background', started: new Date(Date.now() + 1_000).toISOString() },
      { run_id: 'r_live', state: 'running', mode: 'foreground', started: '2020-01-01T00:00:00Z' },
      { run_id: 'r_to', state: 'timeout', mode: 'overnight', started: new Date(Date.now() + 2_000).toISOString() },
      { run_id: 'r_p', state: 'paused', mode: 'foreground', started: new Date().toISOString() },
    ]
    const { sources, f } = make({ [`${ENDPOINTS.agent}/agents/runs`]: () => ({ json: list }) })
    expect(await sources.runs!()).toEqual([
      { id: 'r_new', mode: 'background', state: 'failed', needsHuman: null },
      { id: 'r_to', mode: 'overnight', state: 'failed', needsHuman: null },
      { id: 'r_p', mode: 'foreground', state: 'paused', needsHuman: null },
    ])
    expect(f.calls[0].url).toBe(`${ENDPOINTS.agent}/agents/runs?person=p_test`)
    list = [{ run_id: 'r_live', state: 'done', mode: 'foreground', started: '2020-01-01T00:00:00Z' }]
    expect(await sources.runs!()).toEqual([{ id: 'r_live', mode: 'foreground', state: 'done', needsHuman: null }]) // it was seen running
  })

  it('briefing and the morning report are read at most every five minutes, and a failed read is tried again', async () => {
    let fail = true
    const { sources, f, tick } = make({
      [`${ENDPOINTS.engine}/briefing`]: () => (fail ? { ok: false } : { json: { data: { generated_at: '2026-11-07T08:00:00Z', cards: [{}, {}] } } }),
      [`${ENDPOINTS.agent}/agents/morning`]: { json: { runs: [{}, {}, {}], queued: [] } },
    })
    expect(await sources.briefing!()).toBeNull()
    fail = false
    expect(await sources.briefing!()).toEqual({ generation: '2026-11-07T08:00:00Z', cards: 2 })
    await sources.briefing!()
    expect(f.calls.filter((c) => c.url.includes('/briefing'))).toHaveLength(2) // the failed read and one good one
    tick(301_000)
    await sources.briefing!()
    expect(f.calls.filter((c) => c.url.includes('/briefing'))).toHaveLength(3)
    expect(f.calls.find((c) => c.url.includes('/briefing'))?.url).toBe(`${ENDPOINTS.engine}/briefing?person=p_test`)

    const m = await sources.morning!()
    expect(m).toMatchObject({ runs: 3, id: '2026-11-07' })
    expect(f.calls.find((c) => c.url.includes('/agents/morning'))?.url).toMatch(/since=/)
  })

  it('without a person there is no briefing to ask for', async () => {
    const { sources, f } = make({ [`${ENDPOINTS.engine}/briefing`]: { json: { data: { cards: [] } } } }, { person: () => null })
    expect(await sources.briefing!()).toBeNull()
    expect(f.calls).toEqual([])
  })

  it('proposals: the ids of the routines the engine says are proposed; left out when the scheduler reports them itself', async () => {
    const { sources } = make({ [`${ENDPOINTS.engine}/routines`]: { json: [{ id: 'r1', status: 'proposed' }, { id: 'r2', status: 'declined' }, { status: 'proposed' }] } })
    expect(await sources.proposals!()).toEqual([{ id: 'r1' }])
    const bound = make({}, { proposals: { setAttention: vi.fn(), noticeChoice: vi.fn() } })
    expect(bound.sources.proposals).toBeUndefined()
  })

  it('services: degraded only after it was up and then failed twice running; one that never came up is not mentioned', async () => {
    let agentUp = false
    let engineUp = true
    const { sources } = make({
      [`${ENDPOINTS.engine}/health`]: () => ({ ok: engineUp }),
      [`${ENDPOINTS.agent}/health`]: () => ({ ok: agentUp }),
    })
    expect(await sources.services!()).toEqual([{ service: 'engine', ok: true }]) // the agent never answered: not degraded
    agentUp = true
    expect(await sources.services!()).toEqual([{ service: 'engine', ok: true }, { service: 'agent', ok: true }])
    agentUp = false
    expect(await sources.services!()).toEqual([{ service: 'engine', ok: true }, { service: 'agent', ok: true }]) // one miss
    expect(await sources.services!()).toEqual([{ service: 'engine', ok: true }, { service: 'agent', ok: false }]) // two in a row
    agentUp = true
    expect((await sources.services!())!.find((s) => s.service === 'agent')?.ok).toBe(true)
    engineUp = false
    await sources.services!()
    expect((await sources.services!())!.find((s) => s.service === 'engine')?.ok).toBe(false)
  })
})
