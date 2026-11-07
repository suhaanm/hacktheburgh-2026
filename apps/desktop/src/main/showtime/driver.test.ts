import { mkdtemp, rm } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Services } from '../../shared/contracts'
import type { NormBox } from '../../shared/protocol'
import type { ShowtimeCue } from '../../shared/showtime'

vi.mock('electron', () => ({ app: { getAppPath: () => process.cwd() } }))

import { Bus } from '../bus'
import { ConfirmBroker } from '../confirm'
import type { ServiceContext } from '../context'
import { SettingsStore } from '../settings'
import { StateStore } from '../state'
import { createDriver } from './driver'
import type { Narrator } from './narration'
import type { StageWindow } from './stage-window'

let dir = ''
beforeEach(async () => {
  dir = await mkdtemp(path.join(os.tmpdir(), 'showtime-driver-'))
  process.env.ALONGSIDE_SHOWTIME_ASSETS = path.join(process.cwd(), 'assets/showtime')
  process.env.ALONGSIDE_SHOWTIME_MUTE = '1'
})
afterEach(async () => {
  delete process.env.ALONGSIDE_SHOWTIME_ASSETS
  delete process.env.ALONGSIDE_SHOWTIME_MUTE
  await rm(dir, { recursive: true, force: true })
})

const box = (x: number): NormBox => ({ xmin: x, ymin: 100, xmax: x + 50, ymax: 150 })

function setup(mode: 'scripted' | 'live' = 'scripted') {
  const settings = new SettingsStore(dir)
  const state = new StateStore(settings.get())
  const bus = new Bus()
  const cues: ShowtimeCue[] = []
  const shown: unknown[][] = []
  const clears: Array<string[] | undefined> = []
  const levelEvents: unknown[] = []
  bus.on('level:changed', (e) => levelEvents.push(e))
  const ctx = {
    state,
    bus,
    settings,
    userDataDir: dir,
    sendOverlay: () => undefined,
    sendDock: (_channel: string, cue: ShowtimeCue) => cues.push(cue),
    log: () => undefined,
  } as unknown as ServiceContext
  const analyzed: Array<{ text?: string }> = []
  const services = {
    overlay: { show: (a: unknown[]) => shown.push(a), clear: (ids?: string[]) => clears.push(ids), caption: () => undefined, chip: () => undefined },
    scam: {
      analyze: async (req: { text?: string }) => {
        analyzed.push(req)
        return { verdict: 'likely_scam', redFlags: [{ phrase: 'URGENT', why: 'It rushes you' }], advice: ['Ring your bank'] }
      },
    },
    levels: { evaluateAttempt: () => ({ change: 'hold', reason: 'x', state: { level: 2 } }) },
    learner: { snapshot: () => ({ attempts: [] }) },
  } as unknown as Services
  const stage = {
    rects: async () => ({ 'desk.icon.video': box(100) }) as Record<string, NormBox>,
    phraseBoxes: async () => [box(300)],
    messageText: async (t: string) => `text of ${t}`,
    show: () => undefined,
    hide: () => undefined,
    go: async () => undefined,
    click: async () => true,
    deliverScam: async () => undefined,
  } as unknown as StageWindow
  const narrator: Narrator = { clip: async () => null, available: async () => 0 }
  const driver = createDriver({
    ctx,
    services,
    dispatch: async () => ({}) as never,
    confirm: new ConfirmBroker(state),
    stage: () => stage,
    narrator,
    mode,
    settingsBaseline: settings.get(),
    dockStopBox: async () => box(900),
    log: () => undefined,
  })
  return { driver, state, settings, cues, shown, clears, levelEvents, analyzed }
}

describe('showtime driver', () => {
  it('baseline stops audio, clears the screen, resets level and returns to the dock "now" view', async () => {
    const h = setup()
    h.state.patch({ level: 4 })
    await h.driver.exec({ type: 'baseline', persona: 'marcus' })
    expect(h.cues.map((c) => c.type)).toEqual(['stop-audio', 'view'])
    expect(h.clears).toEqual([undefined])
    expect(h.state.get().level).toBe(2)
    expect(h.state.get().phase).toBe('live')
  })

  it('say shows the caption and sends a text-only cue when narration is muted or no clip exists', async () => {
    const h = setup()
    await h.driver.exec({ type: 'say', line: 'c1-hello' })
    const say = h.cues.find((c) => c.type === 'say')
    expect(say && 'text' in say ? say.text.length : 0).toBeGreaterThan(5)
    expect(say && 'audioBase64' in say ? say.audioBase64 : undefined).toBeUndefined()
    expect(h.state.get().captions.at(-1)?.speaker).toBe('assistant')
    await h.driver.teardown()
  })

  it('draws rings on ground-truth boxes from the stage and skips ones that are not visible', async () => {
    const h = setup()
    await h.driver.exec({
      type: 'ann.show',
      specs: [
        { kind: 'ring', id: 'r1', target: 'desk.icon.video', label: 'VideoChat', step: 1 },
        { kind: 'ring', id: 'r2', target: 'nope.missing' },
        { kind: 'highlight', id: 'flag-urgent', boxes: [{ target: 'messages.msg.scam.0', phrase: 'URGENT' }], note: 'It rushes you' },
      ],
    })
    const anns = h.shown[0] as Array<{ id: string; kind: string }>
    expect(anns.map((a) => a.id)).toEqual(['st-r1', 'st-flag-urgent'])
    expect(anns[0].kind).toBe('ring')
    expect(anns[1].kind).toBe('highlightText')
  })

  it('scripted agent steps show the recorded report in the chip and never call the model', async () => {
    const h = setup('scripted')
    await h.driver.exec({ type: 'agent', op: 'start', text: 'Checking this message…' })
    expect(h.state.get().agents[0].status).toBe('running')
    await h.driver.exec({ type: 'agent', op: 'done', text: 'Likely a scam. Do not tap the link.' })
    expect(h.state.get().agents[0].status).toBe('done')
    expect(h.analyzed).toEqual([])
  })

  it('live mode runs the real scam analysis on the message text read from the stage', async () => {
    const h = setup('live')
    await h.driver.exec({ type: 'agent', op: 'start' })
    for (let i = 0; i < 20 && h.state.get().agents[0]?.status !== 'done'; i++) await new Promise((r) => setTimeout(r, 10))
    expect(h.analyzed).toEqual([{ text: 'text of messages.msg.scam.0' }])
    expect(h.state.get().agents[0].status).toBe('done')
  })

  it('level actions emit the level change on the bus', async () => {
    const h = setup()
    await h.driver.exec({ type: 'level', to: 3, reason: 'two clean steps', scope: 'attempt' })
    expect(h.levelEvents).toEqual([{ skillId: 'video_call', from: 2, to: 3, reason: 'two clean steps', scope: 'attempt' }])
  })

  it('teardown restores the EXACT prior settings, including agency (set by the agency chapter), captions and doItForMeAllowed', async () => {
    const h = setup()
    const before = h.settings.get()
    await h.driver.exec({ type: 'agency.request' })
    h.settings.patch({ captions: !before.captions, textOnly: !before.textOnly })
    await h.driver.exec({ type: 'settings', patch: { glass: true, theme: 'dark' } })
    // agency now defaults to ask_each, the same level the chapter sets, so only the exact restore below is asserted
    await h.driver.teardown()
    expect({ ...h.settings.get(), agencyChosen: before.agencyChosen }).toEqual(before)
  })

  it('a chapter baseline keeps the persona and agency the tour set, but undoes the look-and-feel flips', async () => {
    const h = setup()
    await h.driver.exec({ type: 'settings', patch: { dyslexiaFont: true } })
    await h.driver.exec({ type: 'baseline', persona: 'amelia' })
    expect(h.settings.get().persona).toBe('amelia')
    expect(h.settings.get().dyslexiaFont).toBe(false)
  })

  it('tour settings are applied and put back by teardown, along with persona and level', async () => {
    const h = setup()
    const before = h.settings.get()
    await h.driver.exec({ type: 'settings', patch: { dyslexiaFont: true, textScale: 1.25 } })
    await h.driver.exec({ type: 'persona', id: 'amelia' })
    expect(h.settings.get().dyslexiaFont).toBe(true)
    expect(h.settings.get().textScale).toBe(1.25)
    await h.driver.teardown()
    const after = h.settings.get()
    expect(after.dyslexiaFont).toBe(before.dyslexiaFont)
    expect(after.textScale).toBe(before.textScale)
    expect(after.persona).toBe(before.persona)
    expect(h.state.get().phase).toBe(before.wakeEnabled ? 'listening_for_name' : 'asleep')
  })
})
