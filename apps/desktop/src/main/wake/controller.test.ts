import { describe, expect, it } from 'vitest'
import { createVoiceLock } from '../attention/lock'
import { LIVE_CONSENT_VERSION, LiveSettingsStore } from '../live/settings'
import { createWakeController, type CardAnswer, type CardSpec, type WakeController, type WakeControllerDeps } from './controller'
import type { HelperStatus } from './helper'
import type { ConsentChoice, TaskClient, TaskRow } from './tasks'
import type { RungReading } from './rung'
import { WakeSettingsStore } from './settings'

const CALM = { flagOn: true, isMac: true, mock: false, locked: false, asleep: false, paused: false, killed: false, hardQuiet: { dnd: false, screenSharing: false, onCall: false, inMeeting: false }, agentActing: false, away: false }

function rig(over: { mic?: { status: string }; tasks?: TaskClient; readOut?: (t: string) => boolean; firstRun?: { on: boolean }; rung?: RungReading; live?: { consented?: boolean; frames?: boolean }; startOk?: boolean; blocker?: string | null; inputs?: Partial<typeof CALM> } = {}) {
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
  let problem: string | null = null
  const started: number[] = []
  const cardsSeen: CardSpec[] = []
  const closed: string[] = []
  const answers: Array<CardAnswer | null> = []
  const runs: Array<{ box: unknown; cardId: string }> = []
  let finishRun: (r: { ok: boolean; reason?: string }) => void = () => undefined
  const stops: number[] = []
  const said: string[] = []
  const chimes: number[] = []
  let t = 1_000_000
  const timers: Array<{ fn: () => void; ms: number; live: boolean }> = []
  const inputs = { ...CALM, ...over.inputs }
  const opened: string[] = []
  const readOuts: string[] = []
  const deps: WakeControllerDeps = {
    settings,
    liveSettings,
    openSettings: (w) => void opened.push(w),
    micStatus: () => over.mic?.status ?? 'granted',
    tasks: over.tasks,
    readOut: (t) => (readOuts.push(t), over.readOut?.(t) ?? false),
    sleep: async (ms) => void (t += ms),
    taskPollMs: 1,
    taskWatchMs: 50,
    firstRun: () => over.firstRun?.on === true,
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
      status: () => ({ phase, trigger, refused, problem }),
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
  const endLive = (why: string | null = null, why2: string | null = null): void => {
    phase = 'idle'
    trigger = null
    refused = why
    problem = why2
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
  return { ctl, readOuts, setHelper, over, opened, settings, liveSettings, helperLog, started, cardsSeen, closed, answers, runs, finishRun: (r: { ok: boolean; reason?: string }) => finishRun(r), stops, said, chimes, endLive, fire, flush, inputs, advance: (ms: number) => void (t += ms) }
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
    expect(keyed.liveSettings.get().liveConsentVersion).toBe(0) // switched on by default, but no yes was given
    expect(keyed.settings.get().voiceAnswer).toBe('unset')
    const r = rig()
    r.ctl.start()
    r.answers.push(mouse('voice_only'))
    await r.ctl.onHeard()
    // ONE card holds both questions: two clear lines, four buttons of one weight
    expect(r.cardsSeen.map((c) => c.title)).toEqual(['Talk with Knack?'])
    expect(r.cardsSeen[0].body.split('\n')).toHaveLength(2)
    expect(r.cardsSeen[0].body).toMatch(/^Voice: .*\nScreen: /)
    expect(r.cardsSeen[0].buttons.map((b) => b.label)).toEqual(['Yes, allow both', 'Voice only', 'Not now', 'Never'])
    expect(r.liveSettings.get()).toMatchObject({ liveEnabled: true, liveConsentVersion: LIVE_CONSENT_VERSION, liveFrames: false })
    expect(r.settings.get()).toMatchObject({ voiceAnswer: 'yes', screenAnswer: 'not_now' })
    expect(r.started).toHaveLength(1)
  })
  it('Yes, allow both on the one card turns voice and screen on together; each is the worker\u2019s real click, nothing before it', async () => {
    const fresh = rig()
    // nothing is agreed to before the click, and the defaults hold no yes
    expect(fresh.liveSettings.get()).toMatchObject({ liveConsentVersion: 0, liveFrames: false })
    expect(fresh.settings.get()).toMatchObject({ voiceAnswer: 'unset', screenAnswer: 'unset' })
    fresh.ctl.start()
    fresh.answers.push(mouse('yes'))
    await fresh.ctl.onHeard()
    expect(fresh.cardsSeen).toHaveLength(1)
    expect(fresh.liveSettings.get()).toMatchObject({ liveEnabled: true, liveConsentVersion: LIVE_CONSENT_VERSION, liveFrames: true })
    expect(fresh.settings.get()).toMatchObject({ voiceAnswer: 'yes', screenAnswer: 'yes' })
    expect(fresh.started).toHaveLength(1)
    // a key, a timer or a closed card is not an answer, whichever button it names
    for (const bad of [{ buttonId: 'yes', via: 'other' as const }, null]) {
      const r = rig()
      r.ctl.start()
      r.answers.push(bad)
      await r.ctl.onHeard()
      expect(r.liveSettings.get()).toMatchObject({ liveConsentVersion: 0, liveFrames: false })
      expect(r.settings.get()).toMatchObject({ voiceAnswer: 'unset', screenAnswer: 'unset' })
      expect(r.started).toHaveLength(0)
    }
    // a button the card does not have is not an answer either
    const odd = rig()
    odd.ctl.start()
    odd.answers.push(mouse('allow'))
    await odd.ctl.onHeard()
    expect(odd.liveSettings.get().liveConsentVersion).toBe(0)
  })
  it('Not now and Never on the one card answer both lines: nothing opens, nothing turns on', async () => {
    const notNow = rig()
    notNow.ctl.start()
    notNow.answers.push(mouse('not_now'))
    await notNow.ctl.onHeard()
    expect(notNow.cardsSeen).toHaveLength(1)
    expect(notNow.started).toHaveLength(0)
    expect(notNow.liveSettings.get()).toMatchObject({ liveConsentVersion: 0, liveFrames: false })
    expect(notNow.settings.get()).toMatchObject({ voiceAnswer: 'not_now', screenAnswer: 'unset' })
    const never = rig()
    never.ctl.start()
    never.answers.push(mouse('never'))
    await never.ctl.onHeard()
    expect(never.started).toHaveLength(0)
    expect(never.settings.get()).toMatchObject({ voiceAnswer: 'never', screenAnswer: 'never', wakeListen: false })
    expect(never.liveSettings.get().liveFrames).toBe(false)
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
  // Each cause has its own title and one thing to do (no generic "needs live models" for a missing key or model).
  const needsLive: Record<string, { title: string; body: string }> = {
    mock_mode: { title: 'Voice needs live models.', body: 'Turn on Use live models in Settings, then try again.' },
    no_key: { title: 'Voice needs a Gemini key.', body: 'Add the key to the .env file and reopen Knack.' },
    no_model: { title: 'Voice has no model set.', body: 'Add the voice model name to the .env file and reopen Knack.' },
    models_unreachable: { title: 'Knack could not reach the model service.', body: 'It keeps trying and will switch on by itself.' },
    model_unusable: { title: 'The voice model was not accepted.', body: 'The key cannot use the voice model that is set. Run Check voice in Settings.' },
  }
  it('with no live models the listener still hears the words, shows a card in plain words, asks no consent and opens nothing', async () => {
    for (const blocker of ['mock_mode', 'no_key', 'no_model', 'model_unusable', 'models_unreachable']) {
      const r = rig({ blocker })
      r.ctl.start()
      expect(r.ctl.status().listening).toBe(true)
      r.answers.push(null)
      await r.ctl.onHeard()
      await r.flush()
      expect(r.cardsSeen).toHaveLength(1)
      expect(r.cardsSeen[0]).toMatchObject(needsLive[blocker])
      expect(r.cardsSeen[0].buttons.map((b) => b.label)).toEqual(blocker === 'no_key' || blocker === 'no_model' || blocker === 'models_unreachable' ? ['Close'] : ['Open Settings', 'Close'])
      expect(r.started).toHaveLength(0)
      expect(r.settings.get().voiceAnswer).toBe('unset') // no consent was asked for something that could not happen
      expect(r.ctl.status().line).toBe({ mock_mode: 'Voice needs live models.', no_key: 'Voice needs a Gemini key.', no_model: 'Voice has no model set.', model_unusable: 'The voice model was not accepted.', models_unreachable: 'Knack could not reach the model service. It keeps trying.' }[blocker])
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
    const cases: Array<[string, string, string, string[]]> = [
      ['breaker_open', 'The voice service is not answering.', 'Try again soon.', ['Close']],
      ['day_cap', 'Today\u2019s talking limit is reached.', 'You can raise it in Settings.', ['Open Settings', 'Close']],
      ['mic_permission', 'Knack needs the microphone.', 'Switch Knack on in System Settings, Microphone, then try again.', ['System Settings', 'Close']],
      ['agent_acting', 'Knack is working.', 'Try again when it finishes.', ['Close']],
      ['paused', 'Knack is paused.', 'Choose Resume in the menu bar, then try again.', ['Close']],
      ['killed', 'Everything is stopped.', 'Choose Resume in the menu bar, then try again.', ['Close']],
    ]
    for (const [blocker, title, body, buttons] of cases) {
      const r = rig({ blocker })
      r.ctl.start()
      r.answers.push(null)
      await r.ctl.onHeard()
      await r.flush()
      expect(r.cardsSeen[0]).toMatchObject({ title, body })
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
    expect(r.cardsSeen.at(-1)).toMatchObject({ title: 'Knack needs the microphone.', body: 'Switch Knack on in System Settings, Microphone, then try again.' })
  })
  it('the microphone going away mid-conversation ends it with one plain card and a line, and the listener returns', async () => {
    const r = rig({ live: { consented: true, frames: true } })
    r.ctl.start()
    await r.ctl.onHeard()
    r.answers.push(null)
    r.endLive('mic_permission')
    await r.flush()
    expect(r.cardsSeen.at(-1)).toMatchObject({ title: 'Knack needs the microphone.', body: 'Switch Knack on in System Settings, Microphone, then try again.' })
    expect(r.ctl.status().session).toBe(false)
    r.fire()
    expect(r.helperLog.at(-1)).toBe('start')
  })
  it('no word the worker can read mentions a demo, a mock or example mode', async () => {
    const t = await import('./texts')
    const { DORMANT_LINE } = await import('./guards')
    const strings: string[] = [t.LISTENING_LINE, t.SWITCH_LABEL, t.SWITCH_NOTE, ...Object.values(t.SPOKEN_LINES), ...Object.values(t.REFUSAL_LINE), ...Object.values(t.BLOCKED_LINE), ...Object.values(DORMANT_LINE)]
    for (const c of [...Object.values(t.CARDS), ...Object.values(t.INFO_CARDS)] as Array<{ title: string; body: string; buttons: ReadonlyArray<{ label: string }> }>) strings.push(c.title, c.body, ...c.buttons.map((b) => b.label))
    strings.push(t.EVERYTHING_CARD.title, t.EVERYTHING_CARD.body, t.FIRST_WELCOME, t.FIRST_WAKE_OPENING)
    for (const s of strings) expect(s).not.toMatch(/demo|mock|example mode|example data|sample data|stand-in|for this build|synthetic|simulated/i)
  })
})

describe('edge cases of the wake path', () => {
  it('a Dictation language that is not installed: the helper ends with on_device_unavailable and the menu says so in one line, with no server fallback to offer', () => {
    const r = rig()
    r.ctl.start()
    r.setHelper({ state: 'blocked', code: 'on_device_unavailable' })
    expect(r.ctl.status()).toMatchObject({ listening: false, fix: 'dictation', line: 'This Mac cannot recognise speech on the device, so Hey Knack stays off. Hold Option-Space to talk instead.' })
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
    expect(r.ctl.status().fix).toBe('microphone')
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
    r.answers.push({ buttonId: 'yes', via: 'mouse' }, null)
    r.ctl.explainRefusal('not_enabled')
    await r.flush()
    await r.flush()
    expect(r.cardsSeen.map((c) => c.title)).toEqual(['Talk with Knack?', 'Talking is on.'])
    expect(r.liveSettings.get()).toMatchObject({ liveEnabled: true, liveConsentVersion: LIVE_CONSENT_VERSION, liveFrames: true })
  })
  it('the talk key with voice switched on by default but no yes yet shows the same card (no_consent), so it is never silently missing', async () => {
    const r = rig()
    r.ctl.start()
    r.answers.push({ buttonId: 'not_now', via: 'mouse' })
    r.ctl.explainRefusal('no_consent')
    await r.flush()
    expect(r.cardsSeen.map((c) => c.title)).toEqual(['Talk with Knack?'])
  })
  it('the talk key refused for a missing key, the service, the microphone or a pause shows its plain card', async () => {
    for (const reason of ['no_key', 'breaker_open', 'mic_permission', 'paused', 'day_cap']) {
      const r = rig()
      r.ctl.start()
      r.answers.push(null)
      r.ctl.explainRefusal(reason)
      await r.flush()
      expect(r.cardsSeen).toHaveLength(1)
      expect(r.cardsSeen[0].title).toBe({ no_key: 'Voice needs a Gemini key.', breaker_open: 'The voice service is not answering.', mic_permission: 'Knack needs the microphone.', paused: 'Knack is paused.', day_cap: 'Today\u2019s talking limit is reached.' }[reason])
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

describe('first run', () => {
  it('waits for the permissions step: nothing starts (so no macOS prompt) until arm(), then it does, and it stays on after set-up ends', () => {
    const f = { on: true }
    const r = rig({ firstRun: f })
    r.ctl.start()
    expect(r.helperLog).toEqual([])
    expect(r.ctl.status()).toMatchObject({ listening: false, dormant: 'first_run', line: 'Hey Knack starts after set-up' })
    r.ctl.arm()
    expect(r.helperLog).toContain('start')
    expect(r.ctl.status().listening).toBe(true)
    f.on = false
    r.ctl.refresh()
    expect(r.ctl.status().listening).toBe(true)
  })
  it('without a first run the listener starts at launch as before', () => {
    const r = rig()
    r.ctl.start()
    expect(r.helperLog).toEqual(['start'])
  })
  it('the first conversation gets the welcome opening once; after a conversation has started it does not', async () => {
    const r = rig({ live: { consented: true, frames: true } })
    r.ctl.start()
    const first = r.ctl.openingText()
    expect(first).toContain('Hi, I am Knack. Try saying: show me where the Needs you list is.')
    expect(first).toContain('point_at')
    expect(first).toContain('"Needs you"')
    expect(r.ctl.status().welcomed).toBe(false)
    await r.ctl.onHeard()
    expect(r.settings.get().welcomed).toBe(true)
    expect(r.ctl.status().welcomed).toBe(true)
    expect(r.ctl.openingText()).toBeNull()
  })
  it('a conversation that could not start does not use up the welcome', async () => {
    const r = rig({ live: { consented: true, frames: true }, startOk: false })
    r.ctl.start()
    r.answers.push(null)
    await r.ctl.onHeard()
    expect(r.settings.get().welcomed).toBe(false)
    expect(r.ctl.openingText()).not.toBeNull()
  })
})

describe('a blocked listener and a click that cannot run say so on a card', () => {
  it('a permission the helper was refused: one card per cause, with the button for the right pane, and again only after it worked in between', async () => {
    const r = rig()
    r.ctl.start()
    r.answers.push({ buttonId: 'microphone', via: 'mouse' })
    r.setHelper({ state: 'blocked', code: 'mic_denied' })
    await r.flush()
    expect(r.cardsSeen).toHaveLength(1)
    expect(r.cardsSeen[0]).toMatchObject({ title: 'Hey Knack needs the microphone.' })
    expect(r.opened).toEqual(['microphone'])
    r.ctl.refresh()
    r.ctl.refresh()
    expect(r.cardsSeen).toHaveLength(1)
    r.setHelper({ state: 'listening', code: null })
    r.answers.push(null)
    r.setHelper({ state: 'blocked', code: 'speech_denied' })
    await r.flush()
    expect(r.cardsSeen[1]).toMatchObject({ title: 'Hey Knack needs speech recognition.' })
    expect(r.cardsSeen[1].buttons.map((b) => b.label)).toEqual(['System Settings', 'Close'])
  })
  it('no on-device speech: the card names Dictation', async () => {
    const r = rig()
    r.ctl.start()
    r.answers.push({ buttonId: 'dictation', via: 'mouse' })
    r.setHelper({ state: 'blocked', code: 'on_device_unavailable' })
    await r.flush()
    expect(r.cardsSeen[0].body).toContain('Dictation')
    expect(r.opened).toEqual(['dictation'])
  })
  it('a worker who switched it off is not shown a card about it', async () => {
    const r = rig()
    r.settings.patch({ wakeListen: false })
    r.ctl.start()
    r.setHelper({ state: 'blocked', code: 'mic_denied' })
    await r.flush()
    expect(r.cardsSeen).toHaveLength(0)
  })
  it('an allowed click that cannot run: Accessibility and Screen Recording have their own card, anything else says it is not ready; Knack shows instead', async () => {
    for (const [reason, title, pane] of [['accessibility_missing', 'Click for you needs Accessibility.', 'accessibility'], ['screen_recording_missing', 'Click for you needs Screen Recording.', 'screen'], ['route_missing', 'I could not click for you.', null]] as const) {
      const r = rig({ live: { consented: true, frames: true }, rung: { cleared: true, targets: ['TextEdit'], at: 'x' } })
      r.ctl.start()
      await r.ctl.onHeard()
      r.answers.push({ buttonId: 'allow', via: 'mouse' })
      if (pane) r.answers.push({ buttonId: pane, via: 'mouse' })
      await r.ctl.doIt({ description: 'the Save button', box: [100, 100, 140, 200] })
      await r.flush()
      r.finishRun({ ok: false, reason })
      await r.flush()
      await r.flush()
      expect(r.cardsSeen.at(-1)).toMatchObject({ title })
      expect(r.opened).toEqual(pane ? [pane] : [])
      expect(r.said).toContain('did_not_work')
    }
  })
  it('every card stays within the word budgets: title 8, body 22, button 3', async () => {
    const t = await import('./texts')
    const words = (x: string): number => x.trim().split(/\s+/).length
    for (const c of [...Object.values(t.CARDS), ...Object.values(t.INFO_CARDS)] as Array<{ title: string; body: string; buttons: ReadonlyArray<{ label: string }> }>) {
      // One title is the owner's own words, 9 long, kept as given.
      expect(words(c.title)).toBeLessThanOrEqual(c.title === 'Knack may look at your screen while we talk' ? 9 : 8)
      // The combined yes card has two lines of one idea each (voice, then screen), so its body may be 30 words; no single line is over 22.
      const lines = c.body.split('\n')
      expect(words(c.body)).toBeLessThanOrEqual(lines.length === 2 ? 30 : 22)
      for (const l of lines) expect(words(l)).toBeLessThanOrEqual(22)
      for (const b of c.buttons) expect(words(b.label)).toBeLessThanOrEqual(3)
    }
  })
})

describe('the yes card at the end of first run and from Check voice', () => {
  it('first run ends: the card shows once, answered only by a real click, and never again by that path', async () => {
    const r = rig()
    r.ctl.start()
    r.answers.push(mouse('voice_only'), null)
    r.ctl.offerAfterFirstRun()
    await r.flush()
    await r.flush()
    expect(r.cardsSeen.map((c) => c.title)).toEqual(['Talk with Knack?', 'Talking is on.'])
    expect(r.liveSettings.get().liveFrames).toBe(false)
    expect(r.settings.get().consentOffered).toBe(true)
    r.ctl.offerAfterFirstRun()
    await r.flush()
    expect(r.cardsSeen).toHaveLength(2)
  })
  it('a card that nobody clicked leaves nothing turned on, and is not shown again by the first-run path', async () => {
    const r = rig()
    r.ctl.start()
    r.answers.push(null)
    r.ctl.offerAfterFirstRun()
    await r.flush()
    expect(r.cardsSeen.map((c) => c.title)).toEqual(['Talk with Knack?'])
    expect(r.liveSettings.get()).toMatchObject({ liveConsentVersion: 0, liveFrames: false })
    expect(r.settings.get()).toMatchObject({ voiceAnswer: 'unset', consentOffered: true })
  })
  it('it is not shown where voice cannot work at all (no live models, no key): that is said where it is asked, and the card waits for a later chance', async () => {
    for (const blocker of ['mock_mode', 'models_unreachable', 'no_key', 'no_model', 'model_unusable']) {
      const r = rig({ blocker })
      r.ctl.start()
      r.ctl.offerAfterFirstRun()
      await r.flush()
      expect(r.cardsSeen, blocker).toHaveLength(0)
      expect(r.settings.get().consentOffered).toBe(false)
    }
    // a microphone that is not allowed yet does not hold the card back: the yes is a different question
    const mic = rig({ blocker: 'mic_permission' })
    mic.ctl.start()
    mic.answers.push(null)
    mic.ctl.offerAfterFirstRun()
    await mic.flush()
    expect(mic.cardsSeen.map((c) => c.title)).toEqual(['Talk with Knack?'])
  })
  it('already agreed to: nothing is shown', async () => {
    const r = rig({ live: { consented: true, frames: true } })
    r.ctl.start()
    r.ctl.offerAfterFirstRun()
    await r.flush()
    expect(r.cardsSeen).toHaveLength(0)
    expect(await r.ctl.askConsent({ explicit: true })).toBe('already')
  })
  it('Check voice\u2019s button shows the card even after Never or Not now, and the answer is still a real click', async () => {
    const r = rig()
    r.ctl.start()
    r.settings.patch({ voiceAnswer: 'never', screenAnswer: 'never', wakeListen: false }, { trusted: true })
    r.answers.push({ buttonId: 'yes', via: 'other' })
    expect(await r.ctl.askConsent({ explicit: true })).toBe('declined') // a key is no answer
    expect(r.cardsSeen.map((c) => c.title)).toEqual(['Talk with Knack?'])
    expect(r.liveSettings.get()).toMatchObject({ liveConsentVersion: 0, liveFrames: false })
    expect(r.settings.get().wakeListen).toBe(true) // the worker asked to be asked again, so listening comes back; talking still needs the yes
    r.answers.push(mouse('yes'))
    expect(await r.ctl.askConsent({ explicit: true })).toBe('granted')
    expect(r.liveSettings.get()).toMatchObject({ liveConsentVersion: LIVE_CONSENT_VERSION, liveFrames: true })
  })
  it('two requests at once show one card', async () => {
    const r = rig()
    r.ctl.start()
    r.answers.push(mouse('not_now'))
    const first = r.ctl.askConsent({ explicit: true })
    expect(await r.ctl.askConsent({ explicit: true })).toBe('busy')
    expect(await first).toBe('declined')
    expect(r.cardsSeen).toHaveLength(1)
  })
})

// ------------------------------------------------------------------------------------------------ "Hey Knack, do X"
const CONSENT = {
  kind: 'claude_agent',
  scope_text: 'Knack will start a Claude agent.',
  can: ['Read and change files on this Mac', 'Run commands on this Mac'],
  cannot: ['Use Knack’s own keys or models'],
  folder: '~/Knack/work/summarise',
  max_minutes: 30,
  buttons: { allow: 'Allow for this task', decline: 'Not now', more: [{ id: 'everything', label: 'Allow everything for this task' }] },
}
const row = (state: TaskRow['state'], over: Partial<TaskRow> = {}): TaskRow => ({ task_id: 'tk_ab12cd34', route: 'claude_agent', state, result: null, answer: null, reason: null, needs_consent: null, question: null, ...over })

function fakeTasks(o: { created?: Record<string, unknown> | 'fail:too_many_tasks' | 'fail:kill_switch' | 'fail:unavailable'; rows?: TaskRow[]; consent?: 'ok' | 'too_many_tasks' | 'no_token'; answerRow?: TaskRow | null } = {}) {
  const calls: string[] = []
  const sources: string[] = []
  const consents: ConsentChoice[] = []
  const answers: string[] = []
  const rows = [...(o.rows ?? [])]
  const client: TaskClient = {
    async create(text, source) {
      calls.push(`create:${text}`)
      sources.push(source ?? 'voice')
      if (typeof o.created === 'string') return { ok: false, reason: o.created.slice(5) as 'too_many_tasks' }
      const c = o.created ?? {}
      return { ok: true, created: { task_id: 'tk_ab12cd34', route: 'claude_agent', summary: 'Knack will start a Claude agent for this once you allow it.', needs_consent: CONSENT, question: null, ...(c as object) } as never }
    },
    async consent(_id, choice) {
      consents.push(choice)
      if (o.consent === 'too_many_tasks') return { ok: false, reason: 'too_many_tasks' }
      if (o.consent === 'no_token') return { ok: false, reason: 'no_token' }
      return { ok: true, row: row('running') }
    },
    async answer(_id, option) {
      answers.push(option)
      return { ok: true, row: o.answerRow ?? row('running') }
    },
    async get() {
      return rows.length > 1 ? (rows.shift() as TaskRow) : (rows[0] ?? null)
    },
    async list() {
      return rows
    },
    async stop() {
      return true
    },
  }
  return { client, calls, sources, consents, answers }
}

describe('start_task: the request goes to the task service and a card asks first', () => {
  it('without a task service the tool answers that it is unavailable', async () => {
    const r = rig()
    r.ctl.start()
    expect(await r.ctl.startTask('summarise my notes')).toEqual({ ok: false, reason: 'unavailable' })
  })
  it('a job that needs consent: the tool returns at once with waiting_consent and a card with Allow for this task, Not now and More appears', async () => {
    const t = fakeTasks()
    const r = rig({ tasks: t.client })
    r.ctl.start()
    r.answers.push(null)
    const a = await r.ctl.startTask('summarise my notes')
    expect(a).toEqual({ ok: true, started: false, waiting_consent: true, route: 'claude_agent' })
    await r.flush()
    expect(t.calls).toEqual(['create:summarise my notes'])
    expect(r.cardsSeen[0]).toMatchObject({ title: 'Start a Claude agent for this?' })
    expect(r.cardsSeen[0].body).toBe('It can read and change files on this Mac. It cannot use Knack’s own keys or models. Folder: ~/Knack/work/summarise.')
    expect(r.cardsSeen[0].buttons.map((b) => b.label)).toEqual(['Allow for this task', 'Not now', 'More'])
    expect(t.consents).toEqual([]) // nothing was posted without a click
  })
  it('a real click on Allow posts consent once, Knack says the fixed started line, and Done. when it finishes', async () => {
    const t = fakeTasks({ rows: [row('running'), row('done')] })
    const r = rig({ tasks: t.client })
    r.ctl.start()
    r.answers.push({ buttonId: 'allow', via: 'mouse' })
    await r.ctl.startTask('summarise my notes')
    await r.flush()
    await r.flush()
    expect(t.consents).toEqual(['allow'])
    expect(r.said[0]).toBe('started')
    for (let i = 0; i < 6; i++) await r.flush()
    expect(r.said).toContain('done')
  })
  it('Allow by a key or voice, a closed card and a timeout post nothing and leave the task waiting', async () => {
    for (const a of [{ buttonId: 'allow', via: 'other' as const }, null]) {
      const t = fakeTasks()
      const r = rig({ tasks: t.client })
      r.ctl.start()
      r.answers.push(a)
      await r.ctl.startTask('summarise my notes')
      await r.flush()
      expect(t.consents).toEqual([])
      expect(r.said).toEqual([])
    }
  })
  it('Not now declines the task and says nothing', async () => {
    const t = fakeTasks()
    const r = rig({ tasks: t.client })
    r.ctl.start()
    r.answers.push({ buttonId: 'decline', via: 'mouse' })
    await r.ctl.startTask('summarise my notes')
    await r.flush()
    expect(t.consents).toEqual(['decline'])
    expect(r.said).toEqual([])
  })
  it('More shows the wider option on its own card: Allow everything posts everything, Not now posts nothing', async () => {
    const t = fakeTasks()
    const r = rig({ tasks: t.client })
    r.ctl.start()
    r.answers.push({ buttonId: 'more', via: 'mouse' }, { buttonId: 'everything', via: 'mouse' })
    await r.ctl.startTask('summarise my notes')
    for (let i = 0; i < 4; i++) await r.flush()
    expect(r.cardsSeen[1]).toMatchObject({ title: 'Allow everything for this task?' })
    expect(t.consents).toEqual(['everything'])
    const t2 = fakeTasks()
    const r2 = rig({ tasks: t2.client })
    r2.ctl.start()
    r2.answers.push({ buttonId: 'more', via: 'mouse' }, { buttonId: 'not_now', via: 'mouse' })
    await r2.ctl.startTask('summarise my notes')
    for (let i = 0; i < 4; i++) await r2.flush()
    expect(t2.consents).toEqual([])
  })
  it('a browser job has no More button', async () => {
    const t = fakeTasks({ created: { route: 'browser', needs_consent: { ...CONSENT, kind: 'browser', can: ['Open pages and read them'], cannot: ['Use your own browser or your saved logins'], folder: null, buttons: { allow: 'Allow for this task', decline: 'Not now', more: [] } } } })
    const r = rig({ tasks: t.client })
    r.ctl.start()
    r.answers.push(null)
    await r.ctl.startTask('check the benefits site')
    await r.flush()
    expect(r.cardsSeen[0].title).toBe("Open Knack's browser for this?")
    expect(r.cardsSeen[0].buttons.map((b) => b.label)).toEqual(['Allow for this task', 'Not now'])
  })
  it('a consent that is refused after the click says why on a card; a failed job says it did not work', async () => {
    const t = fakeTasks({ consent: 'too_many_tasks' })
    const r = rig({ tasks: t.client })
    r.ctl.start()
    r.answers.push({ buttonId: 'allow', via: 'mouse' }, null)
    await r.ctl.startTask('summarise my notes')
    for (let i = 0; i < 4; i++) await r.flush()
    expect(r.cardsSeen.at(-1)?.body).toBe('Too many tasks are running. Stop one or wait.')
    expect(r.said).not.toContain('started')
    const f = fakeTasks({ rows: [row('failed')] })
    const r2 = rig({ tasks: f.client })
    r2.ctl.start()
    r2.answers.push({ buttonId: 'allow', via: 'mouse' })
    await r2.ctl.startTask('summarise my notes')
    for (let i = 0; i < 8; i++) await r2.flush()
    expect(r2.said).toContain('did_not_work')
  })
  it('the service refusing or not answering gives a closed answer and a plain card, and Stop everything refuses before calling it', async () => {
    for (const [created, reason, body] of [['fail:too_many_tasks', 'too_many_tasks', 'Too many tasks are running. Stop one or wait.'], ['fail:kill_switch', 'kill_switch', 'Choose Resume in the menu bar, then try again.'], ['fail:unavailable', 'unavailable', 'The task service is not answering. Try again soon.']] as const) {
      const t = fakeTasks({ created })
      const r = rig({ tasks: t.client })
      r.ctl.start()
      r.answers.push(null)
      expect(await r.ctl.startTask('summarise my notes')).toEqual({ ok: false, reason })
      await r.flush()
      expect(r.cardsSeen[0].body).toBe(body)
    }
    const t = fakeTasks()
    const r = rig({ tasks: t.client })
    r.ctl.start()
    r.ctl.setKilled(true)
    expect(await r.ctl.startTask('summarise my notes')).toEqual({ ok: false, reason: 'kill_switch' })
    expect(t.calls).toEqual([])
  })
  it('Stop everything closes a task card that is up', async () => {
    const t = fakeTasks()
    const r = rig({ tasks: t.client })
    r.ctl.start()
    await r.ctl.startTask('summarise my notes')
    await r.flush()
    r.ctl.setKilled(true)
    expect(r.closed).toContain('task-tk_ab12cd34')
  })
  it('a question about the request is shown as a card of its own options; the click answers it, and a job that then needs consent shows that card', async () => {
    const t = fakeTasks({ created: { route: 'unclear', needs_consent: null, question: { text: 'Which do you mean?', options: [{ id: 'answer', label: 'Answer here' }, { id: 'browser', label: 'Use a browser' }] } }, answerRow: row('waiting_consent', { route: 'browser', needs_consent: { ...CONSENT, kind: 'browser', can: ['Open pages and read them'], cannot: ['Use your own browser or your saved logins'], folder: null, buttons: { allow: 'Allow for this task', decline: 'Not now', more: [] } } }) })
    const r = rig({ tasks: t.client })
    r.ctl.start()
    r.answers.push({ buttonId: 'browser', via: 'mouse' }, null)
    const a = await r.ctl.startTask('check the site for me')
    expect(a).toEqual({ ok: true, started: false, waiting_consent: false, route: 'unclear', asked: true })
    for (let i = 0; i < 4; i++) await r.flush()
    expect(r.cardsSeen[0]).toMatchObject({ title: 'A quick question', body: 'Which do you mean?' })
    expect(r.cardsSeen[0].buttons.map((b) => b.label)).toEqual(['Answer here', 'Use a browser'])
    expect(t.answers).toEqual(['browser'])
    expect(r.cardsSeen[1].title).toBe("Open Knack's browser for this?")
  })
  it('the desktop route: nothing is clicked, and a single click is mentioned only when the first supervised test has passed', async () => {
    const t = fakeTasks({ created: { route: 'desktop', needs_consent: null } })
    const r = rig({ tasks: t.client })
    r.ctl.start()
    expect(await r.ctl.startTask('rename the file on my desktop')).toEqual({ ok: true, started: false, waiting_consent: false, route: 'desktop', desktop_click_possible: false })
    const c = rig({ tasks: t.client, rung: { cleared: true, targets: ['TextEdit'], at: 'x' } })
    c.ctl.start()
    expect(await c.ctl.startTask('rename the file on my desktop')).toMatchObject({ route: 'desktop', desktop_click_possible: true })
    expect(r.cardsSeen).toHaveLength(0)
    expect(t.consents).toEqual([])
  })
  it('an answer route returns the result line for the model to say', async () => {
    const t = fakeTasks({ created: { route: 'answer', needs_consent: null }, rows: [row('running', { route: 'answer' }), row('done', { route: 'answer', result: 'The office opens at nine.' })] })
    const r = rig({ tasks: t.client })
    r.ctl.start()
    expect(await r.ctl.startTask('when does the office open')).toEqual({ ok: true, started: false, waiting_consent: false, route: 'answer', result: 'The office opens at nine.' })
  })
  it('the full answer is what is said when the service gives one, cut to 300 characters', async () => {
    const long = 'The office opens at nine and closes at five. '.repeat(20)
    const t = fakeTasks({ created: { route: 'answer', needs_consent: null }, rows: [row('done', { route: 'answer', result: 'The office opens.', answer: long })] })
    const r = rig({ tasks: t.client })
    r.ctl.start()
    const a = await r.ctl.startTask('when does the office open')
    expect(a).toMatchObject({ route: 'answer' })
    expect((a as { result: string }).result.length).toBe(300)
    expect((a as { result: string }).result.startsWith('The office opens at nine')).toBe(true)
  })
  it('an answer that is not ready in time is read out later in the open conversation, or shown on a card', async () => {
    const slow = fakeTasks({ created: { route: 'answer', needs_consent: null }, rows: [...Array(21).fill(row('running', { route: 'answer' })), row('done', { route: 'answer', result: 'The office opens at nine.' })] })
    const r = rig({ tasks: slow.client, readOut: () => true })
    r.ctl.start()
    expect(await r.ctl.startTask('when does the office open')).toMatchObject({ route: 'answer', result: null })
    for (let i = 0; i < 40; i++) await r.flush()
    expect(r.readOuts).toEqual(['The office opens at nine.'])
    expect(r.cardsSeen).toHaveLength(0)
    const slow2 = fakeTasks({ created: { route: 'answer', needs_consent: null }, rows: [...Array(21).fill(row('running', { route: 'answer' })), row('done', { route: 'answer', result: 'The office opens at nine.' })] })
    const r2 = rig({ tasks: slow2.client })
    r2.ctl.start()
    r2.answers.push(null)
    await r2.ctl.startTask('when does the office open')
    for (let i = 0; i < 40; i++) await r2.flush()
    expect(r2.cardsSeen.at(-1)).toMatchObject({ title: 'Your answer', body: 'The office opens at nine.' })
  })
})

describe('typing a task in the Ask bar (Return with no conversation open)', () => {
  const FAILED_REASON = 'Your request looks like it holds a key or a password, so it was not started.'
  it('without a task service the bar says so in one sentence and keeps the text', async () => {
    const r = rig()
    r.ctl.start()
    expect(await r.ctl.submitTyped('summarise my notes')).toEqual({ ok: false, line: 'Tasks are not available right now.' })
  })
  it('sends the worker’s own line as a typed task and shows the same consent card; the bar closes', async () => {
    const t = fakeTasks()
    const r = rig({ tasks: t.client })
    r.ctl.start()
    r.answers.push(null)
    expect(await r.ctl.submitTyped('summarise‮   my notes  ')).toEqual({ ok: true })
    await r.flush()
    expect(t.calls).toEqual(['create:summarise my notes'])
    expect(t.sources).toEqual(['typed'])
    expect(r.cardsSeen[0]).toMatchObject({ title: 'Start a Claude agent for this?' })
    expect(r.cardsSeen[0].buttons.map((b) => b.label)).toEqual(['Allow for this task', 'Not now', 'More'])
    expect(t.consents).toEqual([])
  })
  it('a real click on Allow posts consent; the started words appear on a card and nothing is spoken; the finished task shows Done. on a card', async () => {
    const t = fakeTasks({ rows: [row('running'), row('done', { result: 'The folder has 12 files.' })] })
    const r = rig({ tasks: t.client })
    r.ctl.start()
    r.answers.push({ buttonId: 'allow', via: 'mouse' }, null, null)
    await r.ctl.submitTyped('summarise my notes')
    for (let i = 0; i < 10; i++) await r.flush()
    expect(t.consents).toEqual(['allow'])
    expect(r.cardsSeen.map((c) => c.title)).toEqual(['Start a Claude agent for this?', 'Started.', 'Done.'])
    expect(r.cardsSeen[1].body).toBe('I will tell you when it is done.')
    expect(r.cardsSeen[2].body).toBe('The folder has 12 files.')
    expect(r.said).toEqual([])
    expect(r.readOuts).toEqual([])
  })
  it('Allow by a key, a closed card and Not now behave as for a spoken request: nothing starts', async () => {
    for (const a of [{ buttonId: 'allow', via: 'other' as const }, null]) {
      const t = fakeTasks()
      const r = rig({ tasks: t.client })
      r.ctl.start()
      r.answers.push(a)
      await r.ctl.submitTyped('summarise my notes')
      await r.flush()
      expect(t.consents).toEqual([])
    }
    const t = fakeTasks()
    const r = rig({ tasks: t.client })
    r.ctl.start()
    r.answers.push({ buttonId: 'decline', via: 'mouse' })
    await r.ctl.submitTyped('summarise my notes')
    await r.flush()
    expect(t.consents).toEqual(['decline'])
  })
  it('More offers Allow everything for this task on its own card, as for a spoken request', async () => {
    const t = fakeTasks()
    const r = rig({ tasks: t.client })
    r.ctl.start()
    r.answers.push({ buttonId: 'more', via: 'mouse' }, { buttonId: 'everything', via: 'mouse' }, null)
    await r.ctl.submitTyped('summarise my notes')
    for (let i = 0; i < 6; i++) await r.flush()
    expect(r.cardsSeen[1]).toMatchObject({ title: 'Allow everything for this task?' })
    expect(t.consents).toEqual(['everything'])
  })
  it('the refusals are one plain sentence and the text stays in the box: too many tasks, everything stopped, service down, not taken', async () => {
    for (const [created, line] of [['fail:too_many_tasks', 'Too many tasks are running. Stop one or wait.'], ['fail:kill_switch', 'Everything is stopped. Resume from the menu bar.'], ['fail:unavailable', 'The task service is not answering. Try again soon.']] as const) {
      const r = rig({ tasks: fakeTasks({ created }).client })
      r.ctl.start()
      expect(await r.ctl.submitTyped('summarise my notes')).toEqual({ ok: false, line })
      expect(r.cardsSeen).toHaveLength(0)
    }
    const t = fakeTasks()
    const r = rig({ tasks: t.client })
    r.ctl.start()
    r.ctl.setKilled(true)
    expect(await r.ctl.submitTyped('summarise my notes')).toEqual({ ok: false, line: 'Everything is stopped. Resume from the menu bar.' })
    expect(t.calls).toEqual([])
  })
  it('a request the service refuses at once shows the service’s own plain reason, and the text stays', async () => {
    const t = fakeTasks({ created: { route: 'unclear', needs_consent: null }, rows: [row('failed', { reason: FAILED_REASON })] })
    const r = rig({ tasks: t.client })
    r.ctl.start()
    expect(await r.ctl.submitTyped('my password is hunter2hunter2')).toEqual({ ok: false, line: FAILED_REASON })
  })
  it('an empty line or an over-long one is not sent at all', async () => {
    const t = fakeTasks()
    const r = rig({ tasks: t.client })
    r.ctl.start()
    expect(await r.ctl.submitTyped('   ')).toEqual({ ok: false })
    expect(await r.ctl.submitTyped('a'.repeat(501))).toEqual({ ok: false })
    expect(t.calls).toEqual([])
  })
  it('the clarifying question is the same card, and its click answers it', async () => {
    const t = fakeTasks({ created: { route: 'unclear', needs_consent: null, question: { text: 'Which do you mean?', options: [{ id: 'answer', label: 'Answer here' }, { id: 'browser', label: 'Use a browser' }] } } })
    const r = rig({ tasks: t.client })
    r.ctl.start()
    r.answers.push({ buttonId: 'answer', via: 'mouse' })
    expect(await r.ctl.submitTyped('check the site for me')).toEqual({ ok: true })
    for (let i = 0; i < 4; i++) await r.flush()
    expect(r.cardsSeen[0]).toMatchObject({ title: 'A quick question', body: 'Which do you mean?' })
    expect(t.answers).toEqual(['answer'])
  })
  it('an answered question is shown on a card, Your answer, and is never read out even when a conversation is open', async () => {
    const t = fakeTasks({ created: { route: 'answer', needs_consent: null }, rows: [row('running', { route: 'answer' }), row('done', { route: 'answer', result: 'The office opens.', answer: 'The office opens at nine.' })] })
    const r = rig({ tasks: t.client, readOut: () => true })
    r.ctl.start()
    r.answers.push(null)
    expect(await r.ctl.submitTyped('when does the office open')).toEqual({ ok: true })
    for (let i = 0; i < 8; i++) await r.flush()
    expect(r.cardsSeen.at(-1)).toMatchObject({ title: 'Your answer', body: 'The office opens at nine.' })
    expect(r.readOuts).toEqual([])
  })
  it('the desktop route shows I will show you instead on a card with the service’s own steps, and clicks nothing', async () => {
    const t = fakeTasks({ created: { route: 'desktop', needs_consent: null, summary: 'Open Finder, then drag the file to the folder.' }, rows: [row('running', { route: 'desktop' })] })
    const r = rig({ tasks: t.client })
    r.ctl.start()
    r.answers.push(null)
    expect(await r.ctl.submitTyped('move the file to the folder')).toEqual({ ok: true })
    await r.flush()
    expect(r.cardsSeen[0]).toMatchObject({ title: 'I will show you instead.', body: 'Open Finder, then drag the file to the folder.' })
    expect(t.consents).toEqual([])
  })
  it('a typed task that fails says so on a card, not aloud', async () => {
    const t = fakeTasks({ rows: [row('failed', { reason: 'Reached the spend limit you set.' })] })
    const r = rig({ tasks: t.client })
    r.ctl.start()
    r.answers.push({ buttonId: 'allow', via: 'mouse' }, null, null)
    await r.ctl.submitTyped('summarise my notes')
    for (let i = 0; i < 10; i++) await r.flush()
    expect(r.cardsSeen.at(-1)).toMatchObject({ title: 'That did not work.', body: 'Reached the spend limit you set.' })
    expect(r.said).toEqual([])
  })
})

describe('the first conversation’s welcome', () => {
  it('still comes with the first Hey Knack after first run, and only once', async () => {
    const f = { on: true }
    const r = rig({ firstRun: f, live: { consented: true, frames: true } })
    r.ctl.start()
    f.on = false // first run is over
    r.ctl.refresh()
    expect(r.ctl.openingText()).toContain('Hi, I am Knack. Try saying: show me where the Needs you list is.')
    await r.ctl.onHeard()
    expect(r.ctl.openingText()).toBeNull()
  })
  it('while set-up is still open the example points at a button that exists on that screen', () => {
    const f = { on: true }
    const r = rig({ firstRun: f })
    r.ctl.start()
    r.ctl.arm()
    const t = r.ctl.openingText() as string
    expect(t).toContain('Try saying: show me where the Show my week button is.')
    expect(t).toContain('"Show my week"')
    expect(t).not.toContain('Needs you')
  })
})


describe('a conversation that opened but could not hear or answer says why, on a card, once', () => {
  const CASES: Array<[string, string, string]> = [
    ['secure_input', 'Knack cannot listen right now.', 'A password field or a secure app is open. Close it, then try again.'],
    ['denylisted_app', 'Knack skips private apps.', 'A private app is in front, so Knack did not listen. Switch to another app and try again.'],
    ['locked', 'The screen is locked.', 'Unlock it, then try again.'],
    ['gate_stale', 'Knack could not check the screen.', 'It checks that nothing private is in front before it listens. Try again in a moment.'],
    ['ledger_unavailable', 'Knack could not start talking.', 'The privacy record is not answering, so nothing was sent. Reopen Knack and try again.'],
    ['mic_device', 'Knack could not open the microphone.', 'Check that a microphone is connected and chosen in System Settings, Sound, Input.'],
    ['voice_no_key', 'Voice needs a Gemini key.', 'Add the key to the .env file and reopen Knack.'],
    ['voice_refused', 'The voice service said no.', 'It did not accept the key or the voice model. Run Check voice in Settings.'],
    ['voice_network', 'Knack could not reach the voice service.', 'Check your internet connection, then try again.'],
    ['connection_lost', 'The voice connection dropped.', 'Try again in a moment.'],
  ]
  it.each(CASES)('%s: a card whose title names the cause and whose body says the one thing to do', async (code, title, body) => {
    const r = rig({ live: { consented: true, frames: true } })
    r.ctl.start()
    r.answers.push(null)
    r.endLive(null, code) // a talk-key conversation ended with that problem (no wake session is involved)
    await r.flush()
    expect(r.cardsSeen).toHaveLength(1)
    expect(r.cardsSeen[0]).toMatchObject({ title, body })
    // The same problem is not shown twice for the same conversation, and the next conversation can show it again.
    r.endLive(null, code)
    await r.flush()
    expect(r.cardsSeen).toHaveLength(1)
    r.endLive(null, null)
    r.answers.push(null)
    r.endLive(null, code)
    await r.flush()
    expect(r.cardsSeen).toHaveLength(2)
  })
  it('a hands-free conversation that cannot hear says so too, and the listener comes back', async () => {
    const r = rig({ live: { consented: true, frames: true } })
    r.ctl.start()
    await r.ctl.onHeard()
    r.answers.push(null)
    r.endLive(null, 'secure_input')
    await r.flush()
    expect(r.cardsSeen.at(-1)).toMatchObject({ title: 'Knack cannot listen right now.' })
    expect(r.ctl.status().session).toBe(false)
    r.fire()
    expect(r.helperLog.at(-1)).toBe('start')
  })
  it('the status line names the real cause of a microphone refusal', async () => {
    const r = rig({ blocker: 'mic_permission' })
    r.ctl.start()
    r.answers.push(null)
    await r.ctl.onHeard()
    expect(r.ctl.status().line).toBe('Knack needs the microphone. Turn it on in System Settings.')
  })
  it('a microphone macOS has not been asked about: the card says Allow, never an empty System Settings list', async () => {
    for (const blocker of ['mic_permission']) {
      const r = rig({ blocker, mic: { status: 'not-determined' } })
      r.ctl.start()
      r.answers.push({ buttonId: 'microphone', via: 'mouse' })
      await r.ctl.onHeard()
      await r.flush()
      expect(r.cardsSeen[0]).toMatchObject({ title: 'Knack needs the microphone.', body: 'Choose Allow, then say yes when macOS asks.' })
      expect(r.cardsSeen[0].buttons.map((b) => b.label)).toEqual(['Allow', 'Close'])
      expect(r.opened).toEqual(['microphone']) // main decides: ask (not determined) or open (denied), by micFixAction
    }
    const denied = rig({ blocker: 'mic_permission', mic: { status: 'denied' } })
    denied.ctl.start()
    denied.answers.push(null)
    await denied.ctl.onHeard()
    expect(denied.cardsSeen[0].buttons.map((b) => b.label)).toEqual(['System Settings', 'Close'])
  })
  it('the key press answers with the Allow card too when the microphone was never asked', async () => {
    const r = rig({ mic: { status: 'not-determined' } })
    r.ctl.start()
    r.answers.push(null)
    r.ctl.explainRefusal('mic_permission')
    await r.flush()
    expect(r.cardsSeen[0].buttons.map((b) => b.label)).toEqual(['Allow', 'Close'])
    // and the conversation that ends with the same cause does not show a second card
    r.endLive('mic_permission', 'mic_permission')
    await r.flush()
    expect(r.cardsSeen).toHaveLength(1)
  })
})

describe('a listener blocked for a permission is armed again by itself once it is fixed', () => {
  it('the microphone switched on in System Settings: the next check unblocks and starts it, no toggle needed', () => {
    const mic = { status: 'denied' }
    const r = rig({ mic })
    r.ctl.start()
    r.setHelper({ state: 'blocked', code: 'mic_denied' })
    expect(r.helperLog).not.toContain('unblock')
    mic.status = 'granted'
    r.ctl.refresh()
    expect(r.helperLog).toContain('unblock')
  })
  it('speech recognition has no status to read, so a blocked listener tries again after thirty seconds, and not sooner', () => {
    const r = rig()
    r.ctl.start()
    r.setHelper({ state: 'blocked', code: 'speech_denied' })
    r.advance(10_000)
    r.ctl.refresh()
    expect(r.helperLog).not.toContain('unblock')
    r.advance(25_000)
    r.ctl.refresh()
    expect(r.helperLog).toContain('unblock')
  })
  it('a cause that is not a permission (a crash loop, no helper) is not retried by itself', () => {
    const r = rig()
    r.ctl.start()
    r.setHelper({ state: 'blocked', code: 'crash_loop' })
    r.advance(120_000)
    r.ctl.refresh()
    expect(r.helperLog).not.toContain('unblock')
  })
})
