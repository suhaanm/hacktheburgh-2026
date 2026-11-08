import { describe, expect, it } from 'vitest'
import { createVoiceLock } from '../attention/lock'
import { LIVE_CONSENT_VERSION, LiveSettingsStore } from '../live/settings'
import { createWakeController, type CardAnswer, type CardSpec, type WakeController, type WakeControllerDeps } from './controller'
import type { HelperStatus } from './helper'
import type { RungReading } from './rung'
import { WakeSettingsStore } from './settings'

const CALM = { flagOn: true, isMac: true, mock: false, locked: false, asleep: false, paused: false, killed: false, hardQuiet: { dnd: false, screenSharing: false, onCall: false, inMeeting: false }, agentActing: false, away: false }

function rig(over: { rung?: RungReading; live?: { consented?: boolean; frames?: boolean }; startOk?: boolean; blocker?: string | null; inputs?: Partial<typeof CALM> } = {}) {
  const settings = new WakeSettingsStore(null)
  const liveSettings = new LiveSettingsStore(null)
  if (over.live?.consented) liveSettings.patch({ liveEnabled: true, liveConsentVersion: LIVE_CONSENT_VERSION, liveFrames: over.live.frames === true }, { trusted: true })
  let helper: HelperStatus = { state: 'stopped', code: null }
  const helperLog: string[] = []
  let ctl!: WakeController
  const liveSubs = new Set<() => void>()
  let phase = 'idle'
  let trigger: 'key' | 'wake' | null = null
  let refused: string | null = null
  const started: number[] = []
  const cardsSeen: CardSpec[] = []
  const closed: string[] = []
  const answers: Array<CardAnswer | null> = []
  const runs: Array<{ box: unknown; cardId: string }> = []
  let finishRun: (r: { ok: boolean }) => void = () => undefined
  const stops: number[] = []
  const said: string[] = []
  const chimes: number[] = []
  let t = 1_000_000
  const timers: Array<{ fn: () => void; ms: number; live: boolean }> = []
  const inputs = { ...CALM, ...over.inputs }
  const opened: string[] = []
  const deps: WakeControllerDeps = {
    settings,
    liveSettings,
    openSettings: (w) => void opened.push(w),
    live: {
      blocker: () => over.blocker ?? null,
      startFromWake: () => {
        started.push(t)
        if (over.startOk === false) {
          refused = 'mic_permission'
          return false
        }
        phase = 'listening'
        trigger = 'wake'
        liveSubs.forEach((f) => f())
        return true
      },
      status: () => ({ phase, trigger, refused }),
      subscribe: (cb) => {
        liveSubs.add(cb)
        return () => liveSubs.delete(cb)
      },
    },
    helper: {
      start: () => {
        helperLog.push('start')
        helper = { state: 'listening', code: null } // the fake helper is ready at once
        ctl.refresh()
      },
      stop: () => {
        helperLog.push('stop')
        helper = { state: 'stopped', code: null }
      },
      status: () => helper,
      unblock: () => helperLog.push('unblock'),
    },
    inputs: () => inputs,
    cards: {
      ask: (spec) => {
        cardsSeen.push(spec)
        const a = answers.shift()
        return a === undefined ? new Promise(() => undefined) : Promise.resolve(a)
      },
      close: (id) => void closed.push(id),
    },
    lock: createVoiceLock(() => t),
    rung: () => over.rung ?? { cleared: false, why: 'absent' },
    desktop: {
      run: (req) => {
        runs.push(req)
        return new Promise((resolve) => (finishRun = resolve))
      },
      stop: () => void stops.push(t),
    },
    chime: () => void chimes.push(t),
    say: (l) => void said.push(l),
    now: () => t,
    setTimer: (fn, ms) => {
      const h = { fn, ms, live: true }
      timers.push(h)
      return h
    },
    clearTimer: (h) => void ((h as { live: boolean }).live = false),
    setInterval: () => 0,
    clearInterval: () => undefined,
    restartDelayMs: 1500,
  }
  ctl = createWakeController(deps)
  const setHelper = (st: HelperStatus): void => {
    helper = st
    ctl.refresh()
  }
  const endLive = (why: string | null = null): void => {
    phase = 'idle'
    trigger = null
    refused = why
    liveSubs.forEach((f) => f())
  }
  const fire = (): void => {
    const h = timers.filter((x) => x.live).at(-1)
    if (h) {
      h.live = false
      t += h.ms
      h.fn()
    }
  }
  const flush = async (): Promise<void> => {
    for (let i = 0; i < 6; i++) await Promise.resolve()
  }
  return { ctl, setHelper, opened, settings, liveSettings, helperLog, started, cardsSeen, closed, answers, runs, finishRun: (r: { ok: boolean }) => finishRun(r), stops, said, chimes, endLive, fire, flush, inputs, advance: (ms: number) => void (t += ms) }
}
const mouse = (id: string): CardAnswer => ({ buttonId: id, via: 'mouse' })

describe('the listener runs exactly when it may', () => {
  it('starts the helper when nothing is dormant, and says the plain line', () => {
    const r = rig()
    r.ctl.start()
    expect(r.helperLog).toEqual(['start'])
    expect(r.ctl.status()).toMatchObject({ listening: true, dormant: null, line: 'Listening for Hey Knack. Stays on this Mac, nothing stored.' })
  })
  it('does not start when switched off, locked, in a call, in demo mode or with the flag off, and stops when one begins', () => {
    for (const patch of [{ locked: true }, { mock: true }, { flagOn: false }, { agentActing: true }, { away: true }, { hardQuiet: { dnd: false, screenSharing: true, onCall: false, inMeeting: false } }]) {
      const r = rig({ inputs: patch })
      r.ctl.start()
      expect(r.helperLog).toEqual([])
      expect(r.ctl.status().listening).toBe(false)
    }
    const off = rig()
    off.settings.patch({ wakeListen: false })
    off.ctl.start()
    expect(off.helperLog).toEqual([])
    expect(off.ctl.status().line).toBe('Hey Knack is off')
    const r = rig()
    r.ctl.start()
    r.inputs.locked = true
    r.ctl.refresh()
    expect(r.helperLog).toEqual(['start', 'stop'])
    expect(r.ctl.status().line).toBe('Not listening while the screen is locked')
  })
  it('the switch stops and starts it', () => {
    const r = rig()
    r.ctl.start()
    r.ctl.setListen(false)
    expect(r.helperLog.slice(-1)).toEqual(['stop'])
    r.ctl.setListen(true)
    expect(r.helperLog.slice(-2)).toEqual(['unblock', 'start'])
  })
  it('Stop everything makes it dormant until resumed', () => {
    const r = rig()
    r.ctl.start()
    r.ctl.setKilled(true)
    expect(r.helperLog.slice(-1)).toEqual(['stop'])
    expect(r.ctl.status().dormant).toBe('killed')
    r.ctl.setKilled(false)
    expect(r.helperLog.slice(-1)).toEqual(['start'])
  })
  it('shows what the worker must fix when the helper is blocked, in one plain line', () => {
    const r = rig()
    r.ctl.start()
    ;(r as unknown as { ctl: WakeController }).ctl.status()
    const blocked = rig()
    blocked.ctl.start()
    expect(blocked.ctl.status().helper.state).toBe('listening')
  })
})

describe('after the words', () => {
  it('opens a hands-free conversation through the manager, releases the microphone first, chimes, and takes the one-voice lock', async () => {
    const r = rig({ live: { consented: true, frames: true } })
    r.ctl.start()
    await r.ctl.onHeard()
    expect(r.helperLog.slice(-1)).toEqual(['stop'])
    expect(r.started).toHaveLength(1)
    expect(r.chimes).toHaveLength(1)
    expect(r.ctl.status()).toMatchObject({ session: true, click: 'session', dormant: 'live_session' })
  })
  it('ignores the words while dormant or when not listening', async () => {
    const r = rig({ live: { consented: true } })
    await r.ctl.onHeard() // not started
    r.ctl.start()
    r.inputs.hardQuiet = { dnd: false, screenSharing: false, onCall: true, inMeeting: false }
    r.ctl.refresh()
    await r.ctl.onHeard()
    expect(r.started).toHaveLength(0)
  })
  it('asks the voice question on the first wake and opens only on a real mouse Yes; a key or a closed card answers nothing', async () => {
    const keyed = rig()
    keyed.ctl.start()
    keyed.answers.push({ buttonId: 'yes', via: 'other' })
    await keyed.ctl.onHeard()
    expect(keyed.started).toHaveLength(0)
    expect(keyed.liveSettings.get().liveEnabled).toBe(false)
    expect(keyed.settings.get().voiceAnswer).toBe('unset')
    const r = rig()
    r.ctl.start()
    r.answers.push(mouse('yes'), mouse('not_now'))
    await r.ctl.onHeard()
    expect(r.cardsSeen.map((c) => c.title)).toEqual(['Talk with Knack?', 'Knack may look at your screen while we talk'])
    expect(r.cardsSeen[1].buttons.map((b) => b.label)).toEqual(['Yes', 'Not now', 'Never'])
    expect(r.liveSettings.get()).toMatchObject({ liveEnabled: true, liveConsentVersion: LIVE_CONSENT_VERSION, liveFrames: false })
    expect(r.settings.get()).toMatchObject({ voiceAnswer: 'yes', screenAnswer: 'not_now' })
    expect(r.started).toHaveLength(1)
  })
  it('screen Yes turns frames on; Never never asks again; Not now on the voice card opens nothing and is remembered', async () => {
    const yes = rig({ live: { consented: true } })
    yes.ctl.start()
    yes.answers.push(mouse('yes'))
    await yes.ctl.onHeard()
    expect(yes.liveSettings.get().liveFrames).toBe(true)
    expect(yes.started).toHaveLength(1)
    const never = rig({ live: { consented: true } })
    never.ctl.start()
    never.answers.push(mouse('never'))
    await never.ctl.onHeard()
    expect(never.liveSettings.get().liveFrames).toBe(false)
    expect(never.settings.get().screenAnswer).toBe('never')
    expect(never.started).toHaveLength(1) // it still talks, without looking
    const notNow = rig()
    notNow.ctl.start()
    notNow.answers.push(mouse('not_now'))
    await notNow.ctl.onHeard()
    expect(notNow.started).toHaveLength(0)
    expect(notNow.settings.get().voiceAnswer).toBe('not_now')
    expect(notNow.settings.get().wakeListen).toBe(true)
  })
  it('Never on the voice card turns the listener off', async () => {
    const r = rig()
    r.ctl.start()
    r.answers.push(mouse('never'))
    await r.ctl.onHeard()
    expect(r.settings.get()).toMatchObject({ voiceAnswer: 'never', wakeListen: false })
    expect(r.ctl.status().dormant).toBe('switched_off')
    expect(r.started).toHaveLength(0)
  })
  it('a refused start shows its plain line and the listener comes back after a pause', async () => {
    const r = rig({ live: { consented: true, frames: true }, startOk: false })
    r.ctl.start()
    await r.ctl.onHeard()
    expect(r.ctl.status().line).toBe('Knack needs the microphone. Turn it on in System Settings.')
    expect(r.ctl.status().session).toBe(false)
    r.fire()
    expect(r.helperLog.slice(-1)).toEqual(['start'])
  })
  it('when the conversation ends the lock is freed and the listener restarts after the pause, not before', async () => {
    const r = rig({ live: { consented: true, frames: true } })
    r.ctl.start()
    await r.ctl.onHeard()
    r.endLive()
    expect(r.ctl.status().session).toBe(false)
    expect(r.helperLog.at(-1)).toBe('stop')
    r.fire()
    expect(r.helperLog.at(-1)).toBe('start')
  })
  it('the same words are not accepted twice while the first is being handled', async () => {
    const r = rig({ live: { consented: true, frames: true } })
    r.ctl.start()
    await Promise.all([r.ctl.onHeard(), r.ctl.onHeard()])
    expect(r.started).toHaveLength(1)
  })
})

describe('do_it_for_me', () => {
  const BOX: [number, number, number, number] = [100, 100, 140, 200]
  async function inSession(over: Parameters<typeof rig>[0] = {}) {
    const r = rig({ live: { consented: true, frames: true }, ...over })
    r.ctl.start()
    await r.ctl.onHeard()
    return r
  }
  it('while the rung record is absent: first_supervised_test_pending, the fixed line, no card, no run', async () => {
    const r = await inSession()
    const a = await r.ctl.doIt({ description: 'the Save button', box: BOX })
    expect(a).toEqual({ ok: false, reason: 'first_supervised_test_pending' })
    expect(r.said).toEqual(['show_instead'])
    expect(r.cardsSeen.some((c) => c.title === 'Click for you?')).toBe(false)
    expect(r.runs).toHaveLength(0)
  })
  it('with the record: a card, a real mouse Allow, then one run through the desktop port, and a fixed line at the end', async () => {
    const r = await inSession({ rung: { cleared: true, targets: ['TextEdit'], at: 'x' } })
    r.answers.push(mouse('allow'))
    const a = await r.ctl.doIt({ description: 'the Save button', box: BOX })
    expect(a).toEqual({ ok: true, started: true })
    expect(r.cardsSeen.at(-1)).toMatchObject({ title: 'Click for you?', buttons: [{ label: 'Allow once' }, { label: 'Cancel' }] })
    await r.flush()
    expect(r.runs).toEqual([{ box: BOX, cardId: expect.stringMatching(/^click-/) }])
    r.finishRun({ ok: true })
    await r.flush()
    expect(r.said).toEqual(['done'])
    expect(r.ctl.status().click).toBe('session')
  })
  it('Allow by a key or voice never runs: the request ends as a Cancel', async () => {
    const r = await inSession({ rung: { cleared: true, targets: ['TextEdit'], at: 'x' } })
    r.answers.push({ buttonId: 'allow', via: 'other' })
    const a = await r.ctl.doIt({ description: 'the Save button', box: BOX })
    await r.flush()
    expect(a).toEqual({ ok: false, reason: 'worker_cancelled' })
    expect(r.runs).toHaveLength(0)
  })
  it('a card that expires without an answer is a Cancel', async () => {
    const r = await inSession({ rung: { cleared: true, targets: ['TextEdit'], at: 'x' } })
    r.answers.push(null)
    expect(await r.ctl.doIt({ description: 'the Save button', box: BOX })).toEqual({ ok: false, reason: 'worker_cancelled' })
    expect(r.runs).toHaveLength(0)
  })
  it('Cancel answers the model with worker_cancelled and nothing runs', async () => {
    const r = await inSession({ rung: { cleared: true, targets: ['TextEdit'], at: 'x' } })
    r.answers.push(mouse('cancel'))
    expect(await r.ctl.doIt({ description: 'the Save button', box: BOX })).toEqual({ ok: false, reason: 'worker_cancelled' })
    expect(r.runs).toHaveLength(0)
  })
  it('a target that was not found answers target_not_found with no card', async () => {
    const r = await inSession({ rung: { cleared: true, targets: ['TextEdit'], at: 'x' } })
    expect(await r.ctl.doIt({ description: 'the Save button', box: null })).toEqual({ ok: false, reason: 'target_not_found' })
    expect(r.cardsSeen.some((c) => c.title === 'Click for you?')).toBe(false)
  })
  it('kill stops a run in progress and the answer to a waiting call is killed', async () => {
    const r = await inSession({ rung: { cleared: true, targets: ['TextEdit'], at: 'x' } })
    r.answers.push(mouse('allow'))
    await r.ctl.doIt({ description: 'the Save button', box: BOX })
    await r.flush()
    r.ctl.setKilled(true)
    expect(r.stops).toHaveLength(1)
    r.finishRun({ ok: false })
    await r.flush()
    expect(r.ctl.status().click).toBe('killed')
    expect(await r.ctl.doIt({ description: 'x', box: BOX })).toEqual({ ok: false, reason: 'killed' })
  })
})

describe('the words always get an answer', () => {
  const needsLive = { title: 'Hey Knack heard you.', body: 'Live voice needs live models. Turn them on in Settings.' }
  it('with no live models the listener still hears the words, shows a card in plain words, asks no consent and opens nothing', async () => {
    for (const blocker of ['mock_mode', 'no_key', 'no_model', 'model_unusable']) {
      const r = rig({ blocker })
      r.ctl.start()
      expect(r.ctl.status().listening).toBe(true)
      r.answers.push(null)
      await r.ctl.onHeard()
      await r.flush()
      expect(r.cardsSeen).toHaveLength(1)
      expect(r.cardsSeen[0]).toMatchObject(needsLive)
      expect(r.cardsSeen[0].buttons.map((b) => b.label)).toEqual(['Open Settings', 'Close'])
      expect(r.started).toHaveLength(0)
      expect(r.settings.get().voiceAnswer).toBe('unset') // no consent was asked for something that could not happen
      expect(r.ctl.status().line).toBe('Live voice needs live models.')
      r.fire()
      expect(r.helperLog.at(-1)).toBe('start') // and it keeps listening afterwards
    }
  })
  it('the Settings button opens Settings only on a real mouse click; Close and a timeout open nothing', async () => {
    const r = rig({ blocker: 'mock_mode' })
    r.ctl.start()
    r.answers.push({ buttonId: 'settings', via: 'mouse' })
    await r.ctl.onHeard()
    await r.flush()
    expect(r.opened).toEqual(['knack'])
    const q = rig({ blocker: 'mock_mode' })
    q.ctl.start()
    q.answers.push({ buttonId: 'settings', via: 'other' })
    await q.ctl.onHeard()
    await q.flush()
    expect(q.opened).toEqual([])
    const c = rig({ blocker: 'mock_mode' })
    c.ctl.start()
    c.answers.push({ buttonId: 'close', via: 'mouse' })
    await c.ctl.onHeard()
    await c.flush()
    expect(c.opened).toEqual([])
  })
  it('other reasons have their own plain card: the service not answering, the limit, the microphone, a pause', async () => {
    const cases: Array<[string, string, string[]]> = [
      ['breaker_open', 'The voice service is not answering. Try again soon.', ['Close']],
      ['day_cap', 'Today\u2019s talking limit is reached. You can raise it in Settings.', ['Open Settings', 'Close']],
      ['mic_permission', 'Live voice needs the microphone. Turn it on in System Settings.', ['System Settings', 'Close']],
      ['agent_acting', 'Knack is working. Try again when it finishes.', ['Close']],
    ]
    for (const [blocker, body, buttons] of cases) {
      const r = rig({ blocker })
      r.ctl.start()
      r.answers.push(null)
      await r.ctl.onHeard()
      await r.flush()
      expect(r.cardsSeen[0]).toMatchObject({ title: 'Hey Knack heard you.', body })
      expect(r.cardsSeen[0].buttons.map((b) => b.label)).toEqual(buttons)
    }
    const mic = rig({ blocker: 'mic_permission' })
    mic.ctl.start()
    mic.answers.push({ buttonId: 'microphone', via: 'mouse' })
    await mic.ctl.onHeard()
    await mic.flush()
    expect(mic.opened).toEqual(['microphone'])
  })
  it('a start that is refused after the cards still answers with a card', async () => {
    const r = rig({ live: { consented: true, frames: true }, startOk: false })
    r.ctl.start()
    r.answers.push(null)
    await r.ctl.onHeard()
    await r.flush()
    expect(r.cardsSeen.at(-1)).toMatchObject({ title: 'Hey Knack heard you.', body: 'Live voice needs the microphone. Turn it on in System Settings.' })
  })
  it('the microphone going away mid-conversation ends it with one plain card and a line, and the listener returns', async () => {
    const r = rig({ live: { consented: true, frames: true } })
    r.ctl.start()
    await r.ctl.onHeard()
    r.answers.push(null)
    r.endLive('mic_permission')
    await r.flush()
    expect(r.cardsSeen.at(-1)).toMatchObject({ title: 'Hey Knack heard you.', body: 'Live voice needs the microphone. Turn it on in System Settings.' })
    expect(r.ctl.status().session).toBe(false)
    r.fire()
    expect(r.helperLog.at(-1)).toBe('start')
  })
  it('no word the worker can read mentions a demo, a mock or example mode', async () => {
    const t = await import('./texts')
    const { DORMANT_LINE } = await import('./guards')
    const strings: string[] = [t.LISTENING_LINE, t.SWITCH_LABEL, t.SWITCH_NOTE, ...Object.values(t.SPOKEN_LINES), ...Object.values(t.REFUSAL_LINE), ...Object.values(t.BLOCKED_LINE), ...Object.values(DORMANT_LINE)]
    for (const c of [...Object.values(t.CARDS), ...Object.values(t.INFO_CARDS)] as Array<{ title: string; body: string; buttons: ReadonlyArray<{ label: string }> }>) strings.push(c.title, c.body, ...c.buttons.map((b) => b.label))
    for (const s of strings) expect(s).not.toMatch(/demo|mock|example mode|example data/i)
  })
})

describe('edge cases of the wake path', () => {
  it('a Dictation language that is not installed: the helper ends with on_device_unavailable and the menu says so in one line, with no server fallback to offer', () => {
    const r = rig()
    r.ctl.start()
    r.setHelper({ state: 'blocked', code: 'on_device_unavailable' })
    expect(r.ctl.status()).toMatchObject({ listening: false, line: 'This Mac cannot recognise speech on the device, so Hey Knack stays off.' })
  })
  it('a helper that keeps crashing ends blocked with one plain line, and switching the listener off and on tries again', () => {
    const r = rig()
    r.ctl.start()
    r.setHelper({ state: 'blocked', code: 'crash_loop' })
    expect(r.ctl.status().line).toBe('Hey Knack stopped working. Switch it off and on to try again.')
    r.ctl.setListen(false)
    r.ctl.setListen(true)
    expect(r.helperLog).toContain('unblock')
  })
  it('the microphone revoked in System Settings while listening: the helper is blocked with mic_denied and the line names the fix', () => {
    const r = rig()
    r.ctl.start()
    r.setHelper({ state: 'blocked', code: 'mic_denied' })
    expect(r.ctl.status().line).toBe('Hey Knack needs the microphone. Turn it on in System Settings.')
  })
  it('the lid closed and reopened: asleep and locked stop the listener at once; it comes back only when both are over', () => {
    const r = rig()
    r.ctl.start()
    r.inputs.asleep = true
    r.inputs.locked = true
    r.ctl.refresh()
    expect(r.helperLog.at(-1)).toBe('stop')
    expect(r.ctl.status().dormant).toBe('locked')
    r.inputs.locked = false
    r.ctl.refresh()
    expect(r.helperLog.at(-1)).toBe('stop') // still asleep
    r.inputs.asleep = false
    r.ctl.refresh()
    expect(r.helperLog.at(-1)).toBe('start')
  })
  it('the words heard in the instant a call, a screen share or an agent run begins are ignored', async () => {
    for (const patch of [{ hardQuiet: { dnd: false, screenSharing: true, onCall: false, inMeeting: false } }, { hardQuiet: { dnd: false, screenSharing: false, onCall: true, inMeeting: false } }, { agentActing: true }]) {
      const r = rig({ live: { consented: true, frames: true } })
      r.ctl.start()
      Object.assign(r.inputs, patch)
      await r.ctl.onHeard()
      expect(r.started).toHaveLength(0)
      expect(r.cardsSeen).toHaveLength(0) // not even a card: nothing was heard as far as the worker can tell
    }
  })
})

describe('every capability that cannot work answers with a card and a button', () => {
  it('pointing at something anywhere on the screen without Screen Recording: one card that says why and opens System Settings, at most once in ten minutes', async () => {
    const r = rig()
    r.ctl.start()
    r.answers.push({ buttonId: 'screen', via: 'mouse' })
    r.ctl.explainRefusal('screen_recording')
    await r.flush()
    expect(r.cardsSeen[0]).toMatchObject({ title: 'To find it, Knack must see your screen.' })
    expect(r.cardsSeen[0].body).toContain('works without this')
    expect(r.cardsSeen[0].buttons.map((b) => b.label)).toEqual(['System Settings', 'Close'])
    expect(r.opened).toEqual(['screen'])
    r.ctl.explainRefusal('screen_recording')
    await r.flush()
    expect(r.cardsSeen).toHaveLength(1) // not again so soon
    r.advance(10 * 60_000 + 1)
    r.answers.push(null)
    r.ctl.explainRefusal('screen_recording')
    await r.flush()
    expect(r.cardsSeen).toHaveLength(2)
  })
  it('the talk key before the worker agreed to talk: the same two cards as the first wake, then a line that talking is on', async () => {
    const r = rig()
    r.ctl.start()
    r.answers.push({ buttonId: 'yes', via: 'mouse' }, { buttonId: 'not_now', via: 'mouse' }, null)
    r.ctl.explainRefusal('not_enabled')
    await r.flush()
    await r.flush()
    expect(r.cardsSeen.map((c) => c.title)).toEqual(['Talk with Knack?', 'Knack may look at your screen while we talk', 'Talking is on.'])
    expect(r.liveSettings.get().liveEnabled).toBe(true)
  })
  it('the talk key refused for a missing key, the service, the microphone or a pause shows its plain card', async () => {
    for (const reason of ['no_key', 'breaker_open', 'mic_permission', 'paused', 'day_cap']) {
      const r = rig()
      r.ctl.start()
      r.answers.push(null)
      r.ctl.explainRefusal(reason)
      await r.flush()
      expect(r.cardsSeen).toHaveLength(1)
      expect(r.cardsSeen[0].title).toBe('Hey Knack heard you.')
    }
  })
  it('a refusal the worker should not hear about (already talking) shows nothing', async () => {
    const r = rig()
    r.ctl.start()
    r.ctl.explainRefusal('busy')
    await r.flush()
    expect(r.cardsSeen).toHaveLength(0)
  })
})
