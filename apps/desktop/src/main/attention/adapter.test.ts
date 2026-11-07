import { describe, expect, it, vi } from 'vitest'
import { createAttentionAdapter, type AttentionPorts, type NoticeView } from './adapter'
import { createFakeClient } from './client'
import { acquireWithin, createVoiceLock } from './lock'
import { CALM_SIGNALS } from './signals'
import { EMPTY_BADGES, parseNext, type AttentionItem } from './types'

const item = (over: Partial<AttentionItem> = {}): AttentionItem => ({
  id: 'i_one', type: 'approval_blocking', channel: 'toast', text_id: 'approval_blocking', title: 'An approval is waiting', body: 'Approval queue: 1 approval waiting.',
  source: 'Approval queue', count: 1, actions: [{ id: 'open_queue', label: 'Open the queue' }, { id: 'dismiss', label: 'Close' }], priority: 2, new: true, preempt: false,
  reminder: false, display_s: 20, expires_in_s: 100, reason_code: 'shown_break', ...over,
})
const next = (it: AttentionItem | null, needs = 0) =>
  parseNext({ data: { item: it, active: null, badges: { needs_you: needs, waiting: 0, marker: needs ? 'needs_you' : 'none', stopped: false }, digest_ready: false, poll_after_s: 2 } })

function rig(script: Parameters<typeof createFakeClient>[0] = {}) {
  let t = 1_000_000
  const timers: Array<{ at: number; fn: () => void; id: number }> = []
  let tid = 0
  const shown: NoticeView[] = []
  const hidden: string[] = []
  const badges: Array<[number, number]> = []
  const opened: string[] = []
  const ports: AttentionPorts = {
    showNotice: (n) => void shown.push(n),
    hideNotice: (id) => void hidden.push(id),
    setBadges: (b) => void badges.push([b.needs_you, b.waiting]),
    open: (a) => void opened.push(a),
  }
  const lock = createVoiceLock(() => t)
  const fake = createFakeClient(script)
  const adapter = createAttentionAdapter({
    client: fake.client, signals: () => CALM_SIGNALS, ports, lock, now: () => t,
    setTimer: (fn, ms) => {
      timers.push({ at: t + ms, fn, id: ++tid })
      return tid
    },
    clearTimer: (h) => {
      const i = timers.findIndex((x) => x.id === h)
      if (i >= 0) timers.splice(i, 1)
    },
  })
  const advance = (ms: number) => {
    t += ms
    for (const x of [...timers].sort((a, b) => a.at - b.at)) {
      if (x.at <= t) {
        timers.splice(timers.indexOf(x), 1)
        x.fn()
      }
    }
  }
  return { adapter, fake, shown, hidden, badges, opened, lock, advance, now: () => t }
}

describe('the adapter draws what the engine says, once, and holds the voice', () => {
  it('draws a toast, holds the lock for its display, updates the badges, and lets go when it is over', async () => {
    const r = rig({ next: [next(item(), 1)] })
    await r.adapter.pollOnce()
    expect(r.shown).toHaveLength(1)
    expect(r.shown[0]).toMatchObject({ id: 'i_one', title: 'An approval is waiting', displayMs: 20_000, channel: 'toast' })
    expect(r.badges.at(-1)).toEqual([1, 0])
    expect(r.lock.holder()?.owner).toBe('decision')
    r.advance(20_001)
    expect(r.hidden).toEqual(['i_one'])
    expect(r.lock.holder()).toBeNull()
    expect(r.fake.calls.feedback).toEqual([]) // an untouched notice: the engine labels it by itself
  })

  it('an action opens the page and reports followed with the seconds it took; a stale click does nothing', async () => {
    const r = rig({ next: [next(item(), 1)] })
    await r.adapter.pollOnce()
    r.advance(3_000)
    r.adapter.action('i_other', 'open_queue')
    expect(r.opened).toEqual([])
    r.adapter.action('i_one', 'open_queue')
    expect(r.opened).toEqual(['open_queue'])
    expect(r.fake.calls.feedback).toEqual([{ itemId: 'i_one', event: 'followed', seconds: 3 }])
    expect(r.hidden).toEqual(['i_one'])
    expect(r.lock.holder()).toBeNull()
  })

  it('dismiss, not now and never are the three ways to say no', async () => {
    const r = rig({
      next: [
        next(item({ id: 'a', type: 'routine_proposal', priority: 1, actions: [{ id: 'open_routines', label: 'Look at it' }, { id: 'not_now', label: 'Not now' }, { id: 'never', label: 'Never for this' }] })),
      ],
    })
    await r.adapter.pollOnce()
    r.advance(800)
    r.adapter.action('a', 'never')
    expect(r.fake.calls.feedback).toEqual([{ itemId: 'a', event: 'never', seconds: 0.8 }])
    r.fake.push(next(item({ id: 'b', priority: 1 })))
    r.advance(30_000)
    await r.adapter.pollOnce()
    r.adapter.closed('b', 'dismissed')
    expect(r.fake.calls.feedback.at(-1)).toMatchObject({ itemId: 'b', event: 'dismissed' })
  })

  it('never draws over a voice it cannot take: the item goes back to the engine', async () => {
    const r = rig({ next: [next(item())] })
    r.lock.acquire('decision', 20_000) // a permission prompt holds the voice
    await r.adapter.pollOnce()
    expect(r.shown).toEqual([])
    expect(r.fake.calls.feedback).toEqual([{ itemId: 'i_one', event: 'deferred', seconds: undefined }])
  })

  it('a safety item preempts a cue that is up, and the cue is told to hide', async () => {
    const r = rig({ next: [next(item({ id: 's', type: 'injection_pause', priority: 3, preempt: true }))] })
    const hide = vi.fn()
    expect(r.lock.acquire('cue', 12_000, hide)).toBe(true)
    await r.adapter.pollOnce()
    expect(hide).toHaveBeenCalledTimes(1)
    expect(r.shown.map((n) => n.id)).toEqual(['s'])
    expect(r.lock.holder()?.owner).toBe('safety')
  })

  it('a chip or a question card is Cue’s own surface: it is never drawn as a toast here', async () => {
    const r = rig({ next: [next(item({ type: 'cue_cue', channel: 'chip', title: null, body: null, priority: 1 }))] })
    await r.adapter.pollOnce()
    expect(r.shown).toEqual([])
  })

  it('a failed poll changes nothing and does not throw', async () => {
    const r = rig()
    await expect(r.adapter.pollOnce()).resolves.toBeUndefined()
    expect(r.badges).toEqual([])
  })

  it('stop hides what is up and clears the lock', async () => {
    const r = rig({ next: [next(item())] })
    await r.adapter.pollOnce()
    r.adapter.stop()
    expect(r.hidden).toEqual(['i_one'])
    expect(r.lock.holder()).toBeNull()
    expect(r.adapter.current()).toBeNull()
  })

  it('report sends ids and enums with a safe subject and the worker state attached', async () => {
    const r = rig()
    await r.adapter.report({ type: 'run_finished', subject: 'Run #12 / night', outcome: 'done' })
    const ev = r.fake.calls.submit[0]
    expect(ev.subject).toBe('run__12___night')
    expect(ev.state).toBeTruthy()
    expect(Object.keys(ev)).toEqual(expect.arrayContaining(['type', 'subject', 'outcome', 'state']))
  })
})

describe('the Cue port', () => {
  const dec = { kind: 'cue', episode_id: 'e_ABC123', expires_in_s: 12, trigger: 'auto' }

  it('admits a cue when the engine says show, holds the lock for its life, and release gives it back', async () => {
    const r = rig({ submit: () => ({ itemId: 'i_c1', show: true, reason: 'shown_now', coalesced: false }) })
    const port = r.adapter.cuePort()
    const res = await port.admit(dec, () => undefined)
    expect(res).toEqual({ show: true, itemId: 'i_c1' })
    expect(r.fake.calls.submit[0]).toMatchObject({ type: 'cue_cue', subject: 'e_abc123', expires_in_s: 12, asked: false })
    expect(r.lock.holder()?.owner).toBe('cue')
    port.release()
    expect(r.lock.holder()).toBeNull()
  })

  it('a veto from the engine releases the lock and draws nothing', async () => {
    const r = rig({ submit: () => ({ itemId: 'i_c2', show: false, reason: 'dropped_lock', coalesced: false }) })
    const res = await r.adapter.cuePort().admit({ ...dec, kind: 'ask' }, () => undefined)
    expect(res.show).toBe(false)
    expect(r.lock.holder()).toBeNull()
    expect(r.fake.calls.submit[0].type).toBe('cue_ask')
  })

  it('fails closed when the engine does not answer or throws', async () => {
    const down = rig({ submit: () => null })
    expect((await down.adapter.cuePort().admit(dec, () => undefined)).show).toBe(false)
    expect(down.lock.holder()).toBeNull()
    const boom = rig({
      submit: () => {
        throw new Error('down')
      },
    })
    expect((await boom.adapter.cuePort().admit(dec, () => undefined)).show).toBe(false)
    expect(boom.lock.holder()).toBeNull()
  })

  it('a cue never goes up while a toast holds the voice (the engine is not even asked)', async () => {
    const r = rig()
    r.lock.acquire('decision', 20_000)
    const res = await r.adapter.cuePort().admit(dec, () => undefined)
    expect(res.show).toBe(false)
    expect(r.fake.calls.submit).toEqual([])
  })

  it('the worker’s ask is admitted with asked set and preempts a lighter holder', async () => {
    const r = rig()
    const hide = vi.fn()
    r.lock.acquire('notice', 20_000, hide)
    const res = await r.adapter.cuePort().admit({ ...dec, trigger: 'asked' }, () => undefined)
    expect(res.show).toBe(true)
    expect(hide).toHaveBeenCalled()
    expect(r.fake.calls.submit[0].asked).toBe(true)
  })

  it('an unknown kind is not admitted, and feedback forwards ids and seconds only', async () => {
    const r = rig()
    const port = r.adapter.cuePort()
    expect((await port.admit({ ...dec, kind: 'confirm' }, () => undefined)).show).toBe(false)
    port.feedback('i_c1', 'followed', 4)
    port.feedback('', 'shown', 0)
    expect(r.fake.calls.feedback).toEqual([{ itemId: 'i_c1', event: 'followed', seconds: 4 }])
  })
})

describe('the level glance and the permission prompt', () => {
  it('the glance is drawn only when the engine admits it and nothing else is up', async () => {
    const yes = rig({ submit: () => ({ itemId: 'i_g', show: true, reason: 'shown_now', coalesced: false }) })
    expect(await yes.adapter.admitGlance('lv_2')).toBe(true)
    expect(yes.fake.calls.submit[0]).toMatchObject({ type: 'help_level_changed', subject: 'lv_2', expires_in_s: 60 })
    expect(yes.lock.holder()?.owner).toBe('glance')
    yes.adapter.releaseGlance()
    expect(yes.lock.holder()).toBeNull()
    const no = rig({ submit: () => ({ itemId: 'i_g', show: false, reason: 'dropped_flow', coalesced: false }) })
    expect(await no.adapter.admitGlance('lv_3')).toBe(false)
    expect(no.lock.holder()).toBeNull()
    const busy = rig()
    busy.lock.acquire('cue', 12_000)
    expect(await busy.adapter.admitGlance('lv_1')).toBe(false)
    expect(busy.fake.calls.submit).toEqual([])
  })

  it('a permission prompt waits a moment for a cue to finish, then draws anyway rather than be lost', async () => {
    let t = 0
    const lock = createVoiceLock(() => t)
    lock.acquire('cue', 2_000, undefined, 'e_1')
    const sleep = async (ms: number) => void (t += ms)
    expect(await acquireWithin(lock, 'decision', 20_000, 3_000, 'confirm_1', undefined, { now: () => t, sleep })).toBe(true) // the cue ran out inside the wait
    lock.release('decision')
    lock.acquire('safety', 60_000, undefined, 'k')
    expect(await acquireWithin(lock, 'decision', 20_000, 500, 'confirm_2', undefined, { now: () => t, sleep })).toBe(false)
  })
})

describe('the poll loop', () => {
  it('asks again when the engine says to, within 1 and 30 seconds', async () => {
    const delays: number[] = []
    const fake = createFakeClient({ next: [parseNext({ data: { item: null, badges: {}, poll_after_s: 7 } }), parseNext({ data: { item: null, badges: {}, poll_after_s: 120 } }), parseNext({ data: { item: null, badges: {}, poll_after_s: 0.5 } })] })
    const adapter = createAttentionAdapter({
      client: fake.client, signals: () => CALM_SIGNALS, ports: { showNotice: () => undefined, hideNotice: () => undefined, setBadges: () => undefined, open: () => undefined },
      setTimer: (fn, ms) => {
        delays.push(ms)
        if (delays.length < 4) queueMicrotask(fn) // three answers, then the loop is left waiting
        return delays.length
      },
      clearTimer: () => undefined,
    })
    adapter.start()
    await new Promise((r) => setTimeout(r, 20))
    adapter.stop()
    expect(delays.slice(0, 3)).toEqual([7000, 30000, 1000])
  })
})

describe('defaults', () => {
  it('empty badges are quiet', () => {
    expect(EMPTY_BADGES).toEqual({ needs_you: 0, waiting: 0, marker: 'none', stopped: false })
  })
})
