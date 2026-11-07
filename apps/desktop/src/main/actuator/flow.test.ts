import { mkdtempSync, readFileSync, statSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { describe, expect, it, vi } from 'vitest'
import type { Annotation, GroundResult, LessonStep, Shot, Verdict } from '../../shared/protocol'
import { DEFAULT_SETTINGS } from '../../shared/settings'
import { Bus } from '../bus'
import type { ServiceContext } from '../context'
import { createActuator } from './index'
import { APPROVE, createDoItForMe, DECLINE } from './flow'

const SHOT = { id: 's', displayId: 1, widthPx: 100, heightPx: 100, scaleFactor: 2, jpegBase64: 'x', takenAt: 0, overlayHidden: false } as Shot
const BOX = { xmin: 100, ymin: 200, xmax: 200, ymax: 300 }
const found = (label: string): GroundResult => ({ found: true, box: BOX, confidence: 0.9, label, latencyMs: 1, model: 'fake' })
const step = (safetyCritical: boolean): LessonStep => ({ id: 's1', index: 0, instruction: 'Click it', targetDescription: 'a button', expectedOutcome: 'done', hints: { l1: '', l2: '', l3: '' }, safetyCritical })

function setup(opts: { allowed?: boolean; ground?: GroundResult; trusted?: boolean; dryRun?: boolean; choice?: string | null; agents?: unknown[]; skill?: unknown } = {}) {
  const dir = mkdtempSync(path.join(os.tmpdir(), 'dfm-'))
  const bus = new Bus()
  let allowed = opts.allowed ?? true
  const state = { agents: opts.agents ?? [], skill: opts.skill }
  const ctx = { bus, userDataDir: dir, log: vi.fn(), settings: { get: () => ({ ...DEFAULT_SETTINGS, doItForMeAllowed: allowed }) }, state: { get: () => state } } as unknown as ServiceContext
  const shown: Annotation[][] = []
  const cleared: (string[] | undefined)[] = []
  const grounded = vi.fn(async () => opts.ground ?? found('Settings'))
  const verify = vi.fn(async (): Promise<Verdict> => ({ completed: true, confidence: 0.9, evidence: 'changed', uncertain: false }))
  const s = {
    capture: { grab: vi.fn(async () => SHOT) },
    grounder: { ground: grounded },
    overlay: { show: (a: Annotation[]) => void shown.push(a), clear: (ids?: string[]) => void cleared.push(ids) },
    verifier: { verify },
  } as never
  let resolveAsk: (c: string | null) => void = () => undefined
  const ask = vi.fn((_q: string, _o: [string, string]) => (opts.choice !== undefined ? Promise.resolve(opts.choice) : new Promise<string | null>((r) => (resolveAsk = r))))
  const osascript = vi.fn(async (_args: string[]) => undefined)
  const actuator = createActuator({ platform: 'darwin', displayBounds: () => ({ x: 0, y: 0, width: 1000, height: 1000 }), isTrusted: () => opts.trusted ?? true, osascript, dryRun: opts.dryRun ?? false })
  const clickAt = vi.spyOn(actuator, 'clickAt')
  const run = createDoItForMe({ ctx, s, confirm: { ask }, actuator, settleMs: 0 })
  return { run, ctx, bus, dir, shown, cleared, ask, clickAt, osascript, verify, grounded, setAllowed: (v: boolean) => void (allowed = v), resolveAsk: (c: string | null) => resolveAsk(c) }
}
const kinds = (shown: Annotation[][]) => shown.flat().map((a) => a.kind)
const audit = (dir: string) => readFileSync(path.join(dir, 'actions.log'), 'utf8').trim().split('\n').map((l) => JSON.parse(l))

describe('refusals', () => {
  it('refuses when the setting is off: no screen read, no confirm, no click', async () => {
    const t = setup({ allowed: false })
    const r = await t.run({ target: 'Settings icon' })
    expect(r).toMatchObject({ allowed: false, done: false, code: 'setting_off' })
    expect(t.grounded).not.toHaveBeenCalled()
    expect(t.ask).not.toHaveBeenCalled()
    expect(t.clickAt).not.toHaveBeenCalled()
  })

  it.each(['Send', 'Pay now', 'Sign in', 'Delete account', 'Allow', 'Install', 'Accept', 'Password'])('refuses the denylisted label %s: shows ring + "I will leave this one to you", never asks or clicks', async (label) => {
    const t = setup({ ground: found(label), choice: APPROVE })
    const r = await t.run({ target: 'the button' })
    expect(r).toMatchObject({ allowed: false, done: false, code: 'sensitive', label })
    expect(kinds(t.shown)).toEqual(['ring', 'bubble'])
    expect(JSON.stringify(t.shown)).toContain('I will leave this one to you')
    expect(t.ask).not.toHaveBeenCalled()
    expect(t.clickAt).not.toHaveBeenCalled()
  })

  it('also checks the target description, not just the grounded label', async () => {
    const t = setup({ ground: found('OK'), choice: APPROVE })
    expect(await t.run({ target: 'the button that says Submit' })).toMatchObject({ code: 'sensitive', done: false })
    expect(t.clickAt).not.toHaveBeenCalled()
  })

  it('refuses during a safety-critical lesson step (until the step is done)', async () => {
    const t = setup({ choice: APPROVE })
    t.bus.emit('lesson:step', { lessonId: 'l', skillId: 'spot_scam', stepIndex: 0, stepCount: 2, phase: 'started', step: step(true) })
    expect(await t.run({ target: 'Settings icon' })).toMatchObject({ allowed: false, code: 'safety_step' })
    t.bus.emit('lesson:step', { lessonId: 'l', skillId: 'spot_scam', stepIndex: 0, stepCount: 2, phase: 'done' })
    expect(await t.run({ target: 'Settings icon' })).toMatchObject({ allowed: true, code: 'clicked' })
    expect(t.clickAt).toHaveBeenCalledTimes(1)
  })

  it('refuses during a scam check (running agent chip or the spot_scam skill)', async () => {
    const running = setup({ choice: APPROVE, agents: [{ kind: 'scam_check', status: 'running' }] })
    expect(await running.run({ target: 'Settings icon' })).toMatchObject({ allowed: false, code: 'scam_check' })
    const skill = setup({ choice: APPROVE, skill: { id: 'spot_scam' } })
    expect(await skill.run({ target: 'Settings icon' })).toMatchObject({ allowed: false, code: 'scam_check' })
    const finished = setup({ choice: APPROVE, agents: [{ kind: 'scam_check', status: 'done' }] })
    expect(await finished.run({ target: 'Settings icon' })).toMatchObject({ code: 'clicked' })
    expect(running.clickAt).not.toHaveBeenCalled()
    expect(skill.clickAt).not.toHaveBeenCalled()
  })

  it('says it cannot see an ungrounded target and clicks nothing', async () => {
    const t = setup({ ground: { found: false, confidence: 0.1, latencyMs: 1, model: 'fake' }, choice: APPROVE })
    expect(await t.run({ target: 'unicorn' })).toMatchObject({ allowed: true, done: false, code: 'not_found' })
    expect(t.clickAt).not.toHaveBeenCalled()
  })

  it('without the Accessibility permission: explains, shows ring + ghost cursor, never asks or clicks', async () => {
    const t = setup({ trusted: false, choice: APPROVE })
    const r = await t.run({ target: 'Settings icon' })
    expect(r).toMatchObject({ allowed: true, done: false, code: 'accessibility' })
    expect(kinds(t.shown)).toEqual(['ring', 'ghostCursor'])
    expect(t.ask).not.toHaveBeenCalled()
    expect(t.clickAt).not.toHaveBeenCalled()
    expect(t.osascript).not.toHaveBeenCalled()
  })
})

describe('approval flow', () => {
  it('approved: ring + ghost path, confirm wording, ONE click at the box centre, verify, tick, audit (0600, no screen content)', async () => {
    const t = setup({ choice: APPROVE })
    const r = await t.run({ target: 'the grey Settings gear icon' })
    expect(r).toMatchObject({ allowed: true, done: true, code: 'clicked', label: 'Settings', verified: true })
    expect(kinds(t.shown)).toEqual(['ring', 'ghostCursor', 'tick'])
    expect(t.ask).toHaveBeenCalledWith('I\'ll click "Settings" for you. OK?', [APPROVE, DECLINE])
    expect(t.clickAt).toHaveBeenCalledTimes(1)
    expect(t.clickAt).toHaveBeenCalledWith({ x: 150, y: 250 })
    expect(t.osascript).toHaveBeenCalledWith(['-e', 'tell application "System Events" to click at {150, 250}'])
    expect(t.verify).toHaveBeenCalledTimes(1)
    const lines = audit(t.dir)
    expect(lines).toHaveLength(1)
    expect(lines[0]).toMatchObject({ label: 'Settings', approved: true, ok: true, code: 'clicked' })
    expect(Object.keys(lines[0]).sort()).toEqual(['approved', 'code', 'label', 'ok', 't'])
    expect(statSync(path.join(t.dir, 'actions.log')).mode & 0o777).toBe(0o600)
  })

  it('grounds with precise:true', async () => {
    const t = setup({ choice: DECLINE })
    await t.run({ target: 'Settings icon' })
    expect(t.grounded).toHaveBeenCalledWith(expect.objectContaining({ precise: true }))
  })

  it('declined: nothing is clicked, overlay cleared, audited as not approved', async () => {
    const t = setup({ choice: DECLINE })
    const r = await t.run({ target: 'Settings icon' })
    expect(r).toMatchObject({ allowed: true, done: false, code: 'declined' })
    expect(t.clickAt).not.toHaveBeenCalled()
    expect(t.cleared.at(-1)).toEqual(['dfm-ring', 'dfm-ghost', 'dfm-bubble', 'dfm-tick'])
    expect(audit(t.dir)[0]).toMatchObject({ approved: false, ok: false, code: 'declined' })
  })

  it('an unanswered/dismissed confirm (null) counts as no', async () => {
    const t = setup({ choice: null })
    expect(await t.run({ target: 'Settings icon' })).toMatchObject({ code: 'declined', done: false })
    expect(t.clickAt).not.toHaveBeenCalled()
  })

  it('only the exact approve label approves (model text or another string cannot)', async () => {
    const t = setup({ choice: 'yes' })
    expect(await t.run({ target: 'Settings icon' })).toMatchObject({ code: 'declined' })
    expect(t.clickAt).not.toHaveBeenCalled()
  })

  it('Stop while the confirm is pending cancels it and prevents the click', async () => {
    const t = setup()
    const pending = t.run({ target: 'Settings icon' })
    await vi.waitFor(() => expect(t.ask).toHaveBeenCalled())
    t.bus.emit('session:ended', { reason: 'stop' })
    t.resolveAsk(null) // what ConfirmBroker.cancel() does on session end
    expect(await pending).toMatchObject({ allowed: true, done: false, code: 'stopped' })
    expect(t.clickAt).not.toHaveBeenCalled()
    expect(audit(t.dir)[0]).toMatchObject({ approved: false, code: 'stopped' })
  })

  it('Stop racing the approval (answer arrives after Stop) still prevents the click', async () => {
    const t = setup()
    const pending = t.run({ target: 'Settings icon' })
    await vi.waitFor(() => expect(t.ask).toHaveBeenCalled())
    t.bus.emit('session:ended', { reason: 'stop' })
    t.resolveAsk(APPROVE)
    expect(await pending).toMatchObject({ code: 'stopped', done: false })
    expect(t.clickAt).not.toHaveBeenCalled()
  })

  it('switching the setting off while the confirm is open prevents the click', async () => {
    const t = setup()
    const pending = t.run({ target: 'Settings icon' })
    await vi.waitFor(() => expect(t.ask).toHaveBeenCalled())
    t.setAllowed(false)
    t.resolveAsk(APPROVE)
    expect(await pending).toMatchObject({ code: 'setting_off', done: false })
    expect(t.clickAt).not.toHaveBeenCalled()
  })

  it('one click per approval: two calls need two approvals, a refusal in between adds none', async () => {
    const t = setup({ choice: APPROVE })
    await t.run({ target: 'Settings icon' })
    await t.run({ target: 'Settings icon' })
    expect(t.clickAt).toHaveBeenCalledTimes(2)
    expect(t.ask).toHaveBeenCalledTimes(2)
    const declined = setup({ choice: DECLINE })
    await declined.run({ target: 'Settings icon' })
    await declined.run({ target: 'Settings icon' })
    expect(declined.clickAt).not.toHaveBeenCalled()
  })

  it('a failed click is reported honestly and not ticked', async () => {
    const t = setup({ choice: APPROVE })
    t.osascript.mockRejectedValueOnce(new Error('assistive access disabled'))
    const r = await t.run({ target: 'Settings icon' })
    expect(r).toMatchObject({ allowed: true, done: false, code: 'click_failed' })
    expect(t.verify).not.toHaveBeenCalled()
    expect(audit(t.dir)[0]).toMatchObject({ approved: true, ok: false, code: 'click_failed' })
  })

  it('DRYRUN: the whole flow runs, the click is only logged, no verification', async () => {
    const t = setup({ choice: APPROVE, dryRun: true, trusted: false })
    const r = await t.run({ target: 'Settings icon' })
    expect(r).toMatchObject({ allowed: true, done: true, code: 'clicked', dryRun: true })
    expect(t.osascript).not.toHaveBeenCalled()
    expect(t.verify).not.toHaveBeenCalled()
    expect(audit(t.dir)[0]).toMatchObject({ dryRun: true, ok: true })
  })

  it('an uncertain verdict shows the gentle "not yet" mark instead of a tick', async () => {
    const t = setup({ choice: APPROVE })
    t.verify.mockResolvedValueOnce({ completed: true, confidence: 0.4, evidence: 'maybe', uncertain: true })
    const r = await t.run({ target: 'Settings icon' })
    expect(r).toMatchObject({ code: 'clicked', verified: false })
    const tick = t.shown.flat().find((a) => a.kind === 'tick')
    expect(tick).toMatchObject({ ok: false, tone: 'warn' })
  })
})
