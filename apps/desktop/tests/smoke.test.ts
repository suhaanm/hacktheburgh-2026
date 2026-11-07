import { beforeAll, describe, expect, it, vi } from 'vitest'

// services.ts imports the real capture stub, which lazy-imports electron; keep unit tests free of Electron.
vi.mock('electron', () => ({ app: {}, screen: {}, desktopCapturer: {}, ipcMain: {}, globalShortcut: {}, BrowserWindow: class {} }))

import { Bus } from '../src/main/bus'
import { ConfirmBroker } from '../src/main/confirm'
import type { ServiceContext } from '../src/main/context'
import { createServices } from '../src/main/services'
import { SettingsStore } from '../src/main/settings'
import { StateStore } from '../src/main/state'
import { createDispatcher } from '../src/main/tools/dispatcher'
import type { Dispatch } from '../src/main/tools/dispatcher'
import type { OverlayCommand } from '../src/shared/protocol'
import { DEFAULT_SETTINGS, coerceSettings } from '../src/shared/settings'
import type { Services } from '../src/shared/contracts'

let dispatch: Dispatch
let services: Services
let state: StateStore
let confirm: ConfirmBroker
const overlayCmds: OverlayCommand[] = []

beforeAll(() => {
  process.env.ALONGSIDE_MOCK = '1'
  process.env.ALONGSIDE_MOCK_OVERLAY = '1'
  const settings = new SettingsStore(null)
  state = new StateStore(settings.get())
  const ctx: ServiceContext = {
    state,
    bus: new Bus(),
    settings,
    userDataDir: null,
    sendOverlay: (cmd) => overlayCmds.push(cmd),
    sendDock: () => undefined,
    log: () => undefined,
  }
  services = createServices(ctx)
  confirm = new ConfirmBroker(state)
  dispatch = createDispatcher(ctx, services, confirm)
})

describe('dispatcher + mock services', () => {
  it('point_at grounds a target and returns found', async () => {
    const res = await dispatch('point_at', { target: 'Start call button' })
    expect(res).toMatchObject({ found: true })
    expect((res as { confidence: number }).confidence).toBeGreaterThan(0.5)
  })

  it('point_at says it cannot see an absent target', async () => {
    expect(await dispatch('point_at', { target: 'unicorn button' })).toMatchObject({ found: false })
  })

  it('start_lesson plans 4 steps, step_done advances, verify_step completes, end_lesson clears', async () => {
    const started = await dispatch('start_lesson', { goal: 'join a video call with my daughter' })
    expect(started).toMatchObject({ skillId: 'video_call', stepCount: 4 })
    expect(state.get().skill).toMatchObject({ step: 1, stepCount: 4 })

    expect(await dispatch('step_done', {})).toMatchObject({ ok: true, done: false, step: { index: 1 } })
    expect(await dispatch('verify_step', { expected_outcome: 'call window is open' })).toMatchObject({ completed: true })
    expect(await dispatch('end_lesson', { summary: 'done', teachBackScore: 0.8, confidence: 4 })).toEqual({ ok: true })
    expect(state.get().skill).toBeUndefined()
    expect(services.learner.snapshot().attempts.at(-1)).toMatchObject({ skillId: 'video_call', confidence: 4 })
  })

  it('spawn_agent returns an id and the chip finishes', async () => {
    const res = await dispatch('spawn_agent', { kind: 'scam_check', task: 'Your account will be closed, tap here' })
    const agentId = (res as { agentId: string }).agentId
    expect(agentId).toMatch(/^agent-/)
    expect(state.get().agents.find((a) => a.id === agentId)?.status).toBe('running')
    await vi.waitFor(() => expect(state.get().agents.find((a) => a.id === agentId)?.status).toBe('done'), { timeout: 4000 })
  })

  it('rejects unknown tools and bad arguments without throwing', async () => {
    expect(await dispatch('rm_rf', {})).toMatchObject({ error: expect.stringContaining('Unknown tool') })
    expect(await dispatch('point_at', {})).toMatchObject({ error: expect.stringContaining('Bad arguments') })
  })

  it('refuses live-source calls while asleep (screen is only readable during a session)', async () => {
    expect(await dispatch('point_at', { target: 'x' }, 'live')).toEqual({ error: 'No active session' })
  })

  it('ask_user_confirm only resolves through a real answer', async () => {
    const pending = dispatch('ask_user_confirm', { question: 'Send it?', options: ['Yes', 'No'] })
    await vi.waitFor(() => expect(state.get().pendingConfirm).toBeDefined())
    const id = state.get().pendingConfirm?.id as string
    expect(confirm.answer(id, 'Maybe')).toBe(false)
    expect(confirm.answer(id, 'No')).toBe(true)
    expect(await pending).toEqual({ choice: 'No' })
    expect(state.get().pendingConfirm).toBeUndefined()
  })

  it('set_help_level respects a locked level', async () => {
    const settings = new SettingsStore(null)
    settings.patch({ helpLevelMode: 'locked', lockedLevel: 3 })
    const lockedCtx: ServiceContext = { state, bus: new Bus(), settings, userDataDir: null, sendOverlay: () => undefined, sendDock: () => undefined, log: () => undefined }
    const lockedDispatch = createDispatcher(lockedCtx, services, confirm)
    expect(await lockedDispatch('set_help_level', { level: 4 })).toMatchObject({ applied: false })
  })
})

describe('settings', () => {
  it('has the safe defaults from the brief', () => {
    expect(DEFAULT_SETTINGS).toMatchObject({ demoMode: true, doItForMeAllowed: true, carerSharing: false })
  })
  it('keeps valid keys and defaults the rest from a corrupt file', () => {
    expect(coerceSettings({ voiceSpeed: 9, captions: false, junk: 1 })).toMatchObject({ voiceSpeed: 1, captions: false })
  })
})
