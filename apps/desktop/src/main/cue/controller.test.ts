import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Annotation } from '../../shared/protocol'
import { createCueController, type CueControllerDeps, type OverlayPort, type PanelPort } from './controller'
import { FIXTURES } from './fixtures'
import type { Policy } from './guards'
import type { CueView } from './ipc'
import { createFakeEngine } from './source'
import { CUE_TOKENS } from './tokens'
import { createFakeSpeaker, createFakeVoice } from './voice'

const T = CUE_TOKENS.timing
const ON: Policy = { enabled: true, proactivity: 'balanced', quietUntil: null, pausedUntil: null, killed: false, suppressed: null }

function rig(over: Omit<Partial<CueControllerDeps>, 'policy'> & { policy?: Partial<Policy> } = {}) {
  const calls: string[] = []
  const shown: Annotation[][] = []
  const views: CueView[] = []
  const keys: Array<{ answers: number; dismiss: boolean }> = []
  const overlay: OverlayPort = {
    show: (a) => {
      calls.push('overlay.show')
      shown.push(a)
    },
    clear: (ids) => calls.push(`overlay.clear:${(ids ?? []).join(',')}`),
  }
  const panel: PanelPort = {
    set: (v) => {
      calls.push(v ? `panel.${v.mode}` : 'panel.hide')
      views.push(v)
    },
    keys: (k) => keys.push(k),
    dispose: () => calls.push('panel.dispose'),
  }
  const { policy: policyPatch, ...rest } = over
  const engine = rest.engine ?? createFakeEngine()
  const policy = { ...ON, ...(policyPatch ?? {}) }
  const c = createCueController({ engine, overlay, panel, policy: () => policy, settings: () => ({ proactivity: 'balanced', voice: false }), ...rest })
  return { c, calls, shown, views, keys, engine: engine as ReturnType<typeof createFakeEngine>, policy }
}

beforeEach(() => void vi.useFakeTimers({ now: 1_000_000 }))
afterEach(() => void vi.useRealTimers())

describe('polling', () => {
  it('asks the engine about every 1.5 s and does nothing when it has nothing to say', async () => {
    const r = rig()
    r.c.start()
    await vi.advanceTimersByTimeAsync(T.pollMs * 3 + 10)
    expect(r.engine.polls).toHaveLength(3)
    expect(r.calls).toEqual([])
    r.c.dispose()
  })

  it('switched off or killed: the engine is not even asked', async () => {
    for (const policy of [{ enabled: false }, { killed: true }]) {
      const r = rig({ policy })
      r.c.start()
      await vi.advanceTimersByTimeAsync(T.pollMs * 3)
      expect(r.engine.polls).toHaveLength(0)
      r.c.dispose()
    }
  })

  it('tells the engine what only the desktop knows (denylisted app, secure input), the proactivity and, for an ask, that it was asked', async () => {
    const r = rig({ policy: { suppressed: 'secure input' } })
    r.c.start()
    await vi.advanceTimersByTimeAsync(T.pollMs + 5)
    expect(r.engine.polls[0]).toMatchObject({ denied: true, proactivity: 'balanced', voiceOk: false })
    await r.c.poll({ asked: true })
    expect(r.engine.polls[1]).toMatchObject({ asked: true })
    r.c.dispose()
  })

  it('says away when awareness says the worker is not at the screen', async () => {
    const r = rig({ signals: { away: () => true } })
    await r.c.poll()
    expect(r.engine.polls[0]).toMatchObject({ away: true })
    const here = rig()
    await here.c.poll()
    expect(here.engine.polls[0].away).toBeUndefined()
  })

  it('an engine that does not answer leaves what is up alone; garbage is silence', async () => {
    const r = rig({ engine: createFakeEngine([FIXTURES['cue-t2-l2'], { nonsense: true }]) })
    await r.c.poll()
    expect(r.c.visible()?.kind).toBe('cue')
    await r.c.poll() // garbage: parsed to none, takes the cue down
    expect(r.c.visible()).toBeNull()
    await r.c.poll() // null
    expect(r.c.visible()).toBeNull()
  })
})

describe('a cue on the screen', () => {
  it('a cue puts up the ring and the chip, reports shown, and the keys ask only for Alt+Escape', async () => {
    const r = rig({ engine: createFakeEngine([FIXTURES['cue-t2-l2']]) })
    await r.c.poll()
    expect(r.calls).toEqual(['overlay.show', 'panel.chip'])
    expect(r.shown[0].map((a) => `${a.kind}:${a.id}`)).toEqual(['ring:cue-ring-1'])
    expect(r.engine.sent.map((e) => e.event)).toEqual(['shown'])
    expect(r.keys.at(-1)).toEqual({ answers: 0, dismiss: true })
  })

  it('a new cue replaces the old in the same moment: the old marks are cleared and the new shown together', async () => {
    const r = rig({ engine: createFakeEngine([FIXTURES['cue-t2-l2'], { ...(FIXTURES['cue-t2-l1'] as object), episode_id: 'ep-9' }]) })
    await r.c.poll()
    r.calls.length = 0
    await r.c.poll()
    expect(r.calls.slice(0, 3)).toEqual(['overlay.clear:cue-ring-1,cue-tick-1,cue-ghost-1', 'overlay.show', 'panel.chip'])
  })

  it('20 seconds untouched: it goes by itself, with abandoned to the engine; a touch restarts the clock', async () => {
    const r = rig({ engine: createFakeEngine([FIXTURES['cue-t2-l2']]) })
    await r.c.poll()
    await vi.advanceTimersByTimeAsync(15_000)
    r.c.action({ type: 'touch' })
    await vi.advanceTimersByTimeAsync(15_000)
    expect(r.c.visible()).not.toBeNull()
    await vi.advanceTimersByTimeAsync(5_100)
    expect(r.c.visible()).toBeNull()
    expect(r.calls).toContain('panel.hide')
    expect(r.engine.sent.map((e) => `${e.event}:${e.how}`)).toEqual(['shown:null', 'abandoned:timeout'])
    expect(r.keys.at(-1)).toEqual({ answers: 0, dismiss: false })
  })

  it('Escape (or the x): dismissed, and the same cue does not come back', async () => {
    const r = rig({ engine: createFakeEngine([FIXTURES['cue-t2-l2'], FIXTURES['cue-t2-l2']]) })
    await r.c.poll()
    r.c.action({ type: 'dismiss' })
    expect(r.c.visible()).toBeNull()
    await r.c.poll()
    expect(r.c.visible()).toBeNull()
    expect(r.engine.sent.map((e) => e.event)).toEqual(['shown', 'dismissed'])
  })

  it('the kill switch (or turning Cue off) takes it down at once, without waiting for a poll', async () => {
    const r = rig({ engine: createFakeEngine([FIXTURES['cue-t2-l2']]) })
    await r.c.poll()
    r.policy.killed = true
    r.c.refresh()
    expect(r.c.visible()).toBeNull()
    expect(r.calls.at(-1)).toBe('panel.hide')
    expect(r.engine.sent.map((e) => e.event)).toEqual(['shown']) // a kill reports nothing
  })

  it('quiet for an hour from the tray takes it down and keeps the next one away', async () => {
    const r = rig({ engine: createFakeEngine([FIXTURES['cue-t2-l2'], { ...(FIXTURES['cue-t2-l1'] as object), episode_id: 'ep-9' }]) })
    await r.c.poll()
    r.policy.quietUntil = Date.now() + 3_600_000
    r.c.refresh()
    expect(r.c.visible()).toBeNull()
    expect(r.engine.sent.at(-1)).toMatchObject({ event: 'abandoned', how: 'quiet' })
    await r.c.poll()
    expect(r.c.visible()).toBeNull()
  })

  it('a stale ring: the screen changes, the ring and chip go at once; with a grounder that finds it again it returns', async () => {
    const plain = rig({ engine: createFakeEngine([FIXTURES['cue-t2-l2']]) })
    await plain.c.poll()
    plain.c.screenChanged(0.01) // too small to matter
    expect(plain.calls).not.toContain('panel.hide')
    plain.c.screenChanged(0.2)
    expect(plain.calls.slice(-2)).toEqual(['overlay.clear:cue-ring-1,cue-tick-1,cue-ghost-1', 'panel.hide'])
    await vi.advanceTimersByTimeAsync(T.regroundMs + 50)
    expect(plain.c.visible()).toBeNull() // dropped, never left stale
    expect(plain.engine.sent.at(-1)).toMatchObject({ event: 'abandoned', how: 'stale' })

    const found = rig({ engine: createFakeEngine([FIXTURES['cue-t2-l2']]), grounder: { recheck: async () => ({ box: [300, 300, 360, 420] }) } })
    await found.c.poll()
    found.c.screenChanged(0.2)
    await vi.advanceTimersByTimeAsync(5)
    expect(found.c.visible()).not.toBeNull()
    expect(found.calls.at(-2)).toBe('overlay.show')
    expect(found.shown.at(-1)?.[0]).toMatchObject({ kind: 'ring', box: { ymin: 300, xmin: 300, ymax: 360, xmax: 420 } })

    const same = rig({ engine: createFakeEngine([FIXTURES['cue-t2-l2']]), grounder: { recheck: async () => 'same' as const } })
    await same.c.poll()
    const n = same.calls.length
    same.c.screenChanged(0.2)
    await vi.advanceTimersByTimeAsync(5)
    expect(same.calls).toHaveLength(n)
  })
})

describe('the question', () => {
  const ask = () => createFakeEngine([FIXTURES['ask-3']])

  it('shows the card, registers the keys for its options, and answering collapses it into a chip and polls again', async () => {
    const r = rig({ engine: ask() })
    await r.c.poll()
    expect(r.calls).toEqual(['overlay.show', 'panel.question'].filter((c) => c !== 'overlay.show'))
    expect(r.keys.at(-1)).toEqual({ answers: 3, dismiss: true })
    const polls = r.engine.polls.length
    r.c.action({ type: 'answer', id: 'cliff_a' })
    await vi.advanceTimersByTimeAsync(5)
    expect(r.views.at(-1)).toMatchObject({ mode: 'chip', pending: true, from: 'question' })
    expect(r.engine.sent.map((e) => `${e.event}:${e.option_id}`)).toContain('answered:cliff_a')
    expect(r.engine.polls.length).toBe(polls + 1)
    expect(r.keys.at(-1)).toEqual({ answers: 0, dismiss: true })
  })

  it('12 seconds of ignoring dismisses it', async () => {
    const r = rig({ engine: ask() })
    await r.c.poll()
    await vi.advanceTimersByTimeAsync(T.questionIgnoreMs + 50)
    expect(r.c.visible()).toBeNull()
    expect(r.engine.sent.at(-1)).toMatchObject({ event: 'dismissed', how: 'timeout' })
  })

  it('"something else" is answered with "other" and the conversation is only opened if the app provided a way', async () => {
    const converse = vi.fn()
    const r = rig({ engine: ask(), onConverse: converse })
    await r.c.poll()
    r.c.action({ type: 'other' })
    expect(r.engine.sent.at(-1)).toMatchObject({ event: 'answered', option_id: 'other' })
    expect(converse).toHaveBeenCalledOnce()
    const quiet = rig({ engine: ask() })
    await quiet.c.poll()
    expect(() => quiet.c.action({ type: 'other' })).not.toThrow()
  })

  it('the microphone is never opened by default: no voice provided, or the worker has not turned it on, means no listen', async () => {
    const voice = createFakeVoice(['the second one'])
    const off = rig({ engine: ask(), voice, settings: () => ({ proactivity: 'balanced', voice: false }), buildVoiceOn: true, signals: { workerUsedVoice: () => true } })
    await off.c.poll()
    await vi.advanceTimersByTimeAsync(50)
    expect(voice.calls).toBe(0)
    const noUse = rig({ engine: ask(), voice, settings: () => ({ proactivity: 'balanced', voice: true }), buildVoiceOn: true })
    await noUse.c.poll()
    expect(voice.calls).toBe(0)
  })

  it('with the worker\'s voice on and used, a spoken "the second one" answers the card', async () => {
    const voice = createFakeVoice(['the second one'])
    const r = rig({ engine: ask(), voice, settings: () => ({ proactivity: 'balanced', voice: true }), buildVoiceOn: true, signals: { workerUsedVoice: () => true } })
    await r.c.poll()
    await vi.advanceTimersByTimeAsync(5)
    expect(voice.calls).toBe(1)
    expect(r.engine.sent.map((e) => `${e.event}:${e.option_id}`)).toContain('answered:cliff_a')
  })

  it('a voice answer that arrives after the card has gone is ignored', async () => {
    let resolve: (id: string | null) => void = () => undefined
    const voice = { listenOnce: () => new Promise<string | null>((r) => (resolve = r)) }
    const r = rig({ engine: ask(), voice, settings: () => ({ proactivity: 'balanced', voice: true }), buildVoiceOn: true, signals: { workerUsedVoice: () => true } })
    await r.c.poll()
    r.c.action({ type: 'dismiss' })
    resolve('cliff_a')
    await vi.advanceTimersByTimeAsync(5)
    expect(r.engine.sent.some((e) => e.event === 'answered')).toBe(false)
  })
})

describe('nothing speaks by default', () => {
  const t4 = () => createFakeEngine([FIXTURES['cue-t4']])
  const on = { settings: () => ({ proactivity: 'balanced' as const, voice: true }), buildVoiceOn: true }

  it('cueVoice off (the default): the speaker is never called, even for a tier 4 whisper', async () => {
    const speaker = createFakeSpeaker()
    const r = rig({ engine: t4(), speaker, buildVoiceOn: true, signals: { workerUsedVoice: () => true } })
    await r.c.poll()
    expect(speaker.said).toEqual([])
  })

  it('every gate is needed: the build, the worker\'s setting, voice used or asked, not typing', async () => {
    const cases: Array<[string, Omit<Partial<CueControllerDeps>, 'policy'>]> = [
      ['build off', { ...on, buildVoiceOn: false, signals: { workerUsedVoice: () => true } }],
      ['voice not used', { ...on, signals: { workerUsedVoice: () => false } }],
      ['typing', { ...on, signals: { workerUsedVoice: () => true, typingNow: () => true } }],
    ]
    for (const [name, deps] of cases) {
      const speaker = createFakeSpeaker()
      const r = rig({ engine: t4(), speaker, ...deps })
      await r.c.poll()
      expect(speaker.said, name).toEqual([])
    }
  })

  it('with every gate open it registers the line and speaks it once', async () => {
    const lines: Array<[string, string]> = []
    const said: string[] = []
    const speaker = { say: (id: string) => void said.push(id), registerLine: (id: string, text: string) => void lines.push([id, text]) }
    const r = rig({ engine: t4(), speaker, ...on, signals: { workerUsedVoice: () => true } })
    await r.c.poll()
    expect(lines).toEqual([['whisper.write_note', 'Next, copy the figures across.']])
    expect(said).toEqual(['whisper.write_note'])
    expect(r.engine.polls[0]).toMatchObject({ voiceOk: true })
  })

  it('an asked cue may whisper without earlier voice use; the poll says voice_ok only for that', async () => {
    const speaker = createFakeSpeaker()
    const r = rig({ engine: createFakeEngine([{ ...(FIXTURES['cue-t4'] as object), trigger: 'asked' }]), speaker, ...on })
    await r.c.poll({ asked: true })
    expect(r.engine.polls[0]).toMatchObject({ asked: true, voiceOk: true })
    expect(speaker.said).toEqual(['whisper.write_note'])
  })
})

describe('the voice tools\' port', () => {
  it('candidates are the pack steps seen, at most six; showStep shows a chip for a known step and refuses an unknown one', async () => {
    const r = rig({ engine: createFakeEngine([FIXTURES['ask-4']]) })
    await r.c.poll()
    const port = r.c.livePort()
    expect(port.candidates().map((c) => c.id)).toEqual(['read_case', 'calc_a', 'cliff_a', 'write_note'])
    expect(port.showStep('nope')).toEqual({ ok: false, chip: null })
    const shown = port.showStep('cliff_a')
    expect(shown).toEqual({ ok: true, chip: 'Next: Check cliff edges (A)' })
    expect(r.views.at(-1)).toMatchObject({ mode: 'chip', text: 'Next: Check cliff edges (A)' })
  })

  it('askChoice opens the card for 2 to 4 known ids and onAnswer hears the answer, however it came', async () => {
    const r = rig({ engine: createFakeEngine([FIXTURES['ask-4']]) })
    await r.c.poll()
    r.c.action({ type: 'dismiss' })
    const port = r.c.livePort()
    const heard: string[] = []
    const off = port.onAnswer((id) => heard.push(id))
    expect(port.askChoice(['calc_a'])).toBe(false)
    expect(port.askChoice(['calc_a', 'bogus'])).toBe(false)
    expect(port.askChoice(['calc_a', 'cliff_a', 'write_note'])).toBe(true)
    expect(r.views.at(-1)).toMatchObject({ mode: 'question' })
    r.c.action({ type: 'answer', id: 'cliff_a' })
    expect(heard).toEqual(['cliff_a'])
    off()
    expect(port.askChoice(['calc_a', 'cliff_a'])).toBe(true)
    r.c.action({ type: 'other' })
    expect(heard).toEqual(['cliff_a'])
  })

  it('it works while Cue is switched off only as far as the guards allow: nothing is shown', () => {
    const r = rig({ policy: { enabled: false } })
    expect(r.c.livePort().askChoice(['a', 'b'])).toBe(false)
  })
})

describe('the one-voice rule (attention)', () => {
  const port = (show = true) => {
    const log: string[] = []
    let preempt: () => void = () => undefined
    const attention = {
      admit: vi.fn(async (_d: unknown, onPreempt: () => void) => {
        preempt = onPreempt
        log.push('admit')
        return { show, itemId: 'item-1' }
      }),
      release: vi.fn(() => void log.push('release')),
      feedback: vi.fn((_id: string, e: string, s: number) => void log.push(`fb:${e}:${s}`)),
    }
    return { attention, log, preempt: () => preempt() }
  }

  it('a new cue is drawn only when the router says show; the voice is held while it is up and released when it goes', async () => {
    const p = port()
    const r = rig({ engine: createFakeEngine([FIXTURES['cue-t2-l2']]), attention: p.attention })
    await r.c.poll()
    expect(r.c.visible()?.kind).toBe('cue')
    expect(p.attention.admit).toHaveBeenCalledOnce()
    expect(p.attention.release).not.toHaveBeenCalled()
    r.c.action({ type: 'dismiss' })
    expect(p.attention.release).toHaveBeenCalledOnce()
    expect(p.log).toEqual(['admit', 'fb:shown:0', 'fb:dismissed:0', 'release'])
  })

  it('a veto draws nothing, reports nothing to the engine, and does not count as shown', async () => {
    const p = port(false)
    const r = rig({ engine: createFakeEngine([FIXTURES['cue-t2-l2']]), attention: p.attention })
    await r.c.poll()
    expect(r.c.visible()).toBeNull()
    expect(r.calls).toEqual([])
    expect(r.engine.sent).toEqual([])
    expect(p.attention.feedback).not.toHaveBeenCalled()
  })

  it('the same cue growing a tier is a continuation: not asked again', async () => {
    const p = port()
    const r = rig({ engine: createFakeEngine([FIXTURES['cue-t2-l2'], { ...(FIXTURES['cue-t3'] as object), step: (FIXTURES['cue-t2-l2'] as { step: object }).step, target: (FIXTURES['cue-t2-l2'] as { target: object }).target }]), attention: p.attention })
    await r.c.poll()
    await r.c.poll()
    expect(p.attention.admit).toHaveBeenCalledOnce()
    expect(r.shown.at(-1)?.some((m) => m.kind === 'ghostCursor')).toBe(true)
  })

  it('when something more important takes the voice (safety, a decision) the cue hides at once', async () => {
    const p = port()
    const r = rig({ engine: createFakeEngine([FIXTURES['cue-t2-l2']]), attention: p.attention })
    await r.c.poll()
    p.preempt()
    expect(r.c.visible()).toBeNull()
    expect(r.calls.at(-1)).toBe('panel.hide')
    expect(p.attention.release).toHaveBeenCalledOnce()
  })

  it('Cue\'s own rules can still refuse an admitted cue, and then the voice is given straight back', async () => {
    const p = port()
    const r = rig({ engine: createFakeEngine([{ ...(FIXTURES['cue-t2-l2'] as object), why: { level: 4 } }]), attention: p.attention })
    await r.c.poll()
    expect(r.c.visible()).toBeNull()
    expect(p.attention.release).toHaveBeenCalledOnce()
  })

  it('an attention service that fails keeps Cue quiet (fail closed); a question is asked about like a cue', async () => {
    const broken = { admit: async () => Promise.reject(new Error('down')), release: vi.fn() }
    const r = rig({ engine: createFakeEngine([FIXTURES['cue-t2-l2']]), attention: broken })
    await r.c.poll()
    expect(r.c.visible()).toBeNull()
    const p = port()
    const q = rig({ engine: createFakeEngine([FIXTURES['ask-3']]), attention: p.attention })
    await q.c.poll()
    expect(p.attention.admit).toHaveBeenCalledOnce()
    expect(q.c.visible()?.kind).toBe('ask')
  })

  it('a silent confirmation tick needs no voice', async () => {
    const p = port()
    const r = rig({ engine: createFakeEngine([FIXTURES['confirm']]), attention: p.attention })
    await r.c.poll()
    expect(p.attention.admit).not.toHaveBeenCalled()
    expect(r.c.visible()?.kind).toBe('confirm')
  })
})
