import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import type { Services } from '../../../shared/contracts'
import { Bus } from '../../bus'
import type { ServiceContext } from '../../context'
import { mockArchitect, mockCapture, mockGrounder, mockLiveBridge, mockOverlay, mockVerifier } from '../../mocks'
import { SettingsStore } from '../../settings'
import { StateStore } from '../../state'
import { teachingBundle } from '../index'

const dirs: string[] = []
afterEach(() => {
  for (const d of dirs.splice(0)) fs.rmSync(d, { recursive: true, force: true })
})

function wire() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'alongside-bundle-'))
  dirs.push(dir)
  const settings = new SettingsStore(null)
  const ctx: ServiceContext = {
    state: new StateStore(settings.get()),
    bus: new Bus(),
    settings,
    userDataDir: dir,
    sendOverlay: () => undefined,
    sendDock: () => undefined,
    log: () => undefined,
  }
  const s = {} as Services
  s.capture = mockCapture()
  s.grounder = mockGrounder()
  s.verifier = mockVerifier()
  s.architect = mockArchitect()
  s.overlay = mockOverlay(ctx)
  s.live = mockLiveBridge(ctx)
  const bundle = teachingBundle(ctx, s)
  s.learner = bundle.learner
  s.levels = bundle.levels
  s.runner = bundle.runner
  s.teaching = bundle.teaching
  return { ctx, s, bundle, dir }
}

describe('teachingBundle (the services.ts wiring)', () => {
  it('is memoised per context and loads profile.md on first use', async () => {
    const { ctx, s, bundle, dir } = wire()
    expect(teachingBundle(ctx, s)).toBe(bundle)
    await bundle.ready
    expect(fs.existsSync(path.join(dir, 'profile.md'))).toBe(true)
  })

  it('honours the demo seed dropped into userData: prompt carries it and the lesson starts at its level', async () => {
    const { ctx, s, bundle, dir } = wire()
    fs.copyFileSync(path.join(__dirname, '..', 'fixtures', 'demo-profile.md'), path.join(dir, 'profile.md'))
    const text = await s.teaching.systemInstruction('marcus')
    expect(text).toContain('Start a video call: Walk with me')
    expect(text).toContain('phone book')
    const started = await s.runner.start('I want to call Lily')
    expect(started.skillId).toBe('video_call')
    expect(ctx.state.get().level).toBe(2)
    expect(ctx.state.get().skill).toMatchObject({ id: 'video_call', step: 1 })
    await s.runner.abort('test')
    expect(bundle.runner.running).toBe(false)
  })

  it('a reset (deleting profile.md) is picked up at the next lesson', async () => {
    const { ctx, s, dir } = wire()
    fs.copyFileSync(path.join(__dirname, '..', 'fixtures', 'demo-profile.md'), path.join(dir, 'profile.md'))
    await s.runner.start('call Lily')
    await s.runner.abort('x')
    fs.rmSync(path.join(dir, 'profile.md'))
    await s.runner.start('call Lily')
    expect(ctx.state.get().level).toBe(1)
    await s.runner.abort('x')
  })

  it('works with the mock learner in the bag (per-service mock flags)', async () => {
    const { s } = wire()
    s.learner = { ...s.learner, snapshot: s.learner.snapshot.bind(s.learner) }
    await expect(s.teaching.systemInstruction('amelia')).resolves.toContain('You are Amelia')
  })
})
