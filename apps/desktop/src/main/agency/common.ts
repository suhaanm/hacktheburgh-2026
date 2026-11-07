// Shared plumbing for open_for_me and act_for_me: the situation tracker (safety-critical step, scam check, Stop),
// plain-English wording, the policy context, and the real-click confirmation step.
import path from 'node:path'
import os from 'node:os'
import type { Services } from '../../shared/contracts'
import type { Annotation, NormPoint } from '../../shared/protocol'
import type { ConfirmBroker } from '../confirm'
import type { ServiceContext } from '../context'
import type { Actuator } from '../actuator'
import { resolvePane, type ActionKind, type PolicyContext, type ProposedAction } from './policy'

export interface AgencyDeps {
  ctx: ServiceContext
  s: Pick<Services, 'capture' | 'overlay' | 'verifier' | 'learner' | 'files'>
  confirm: Pick<ConfirmBroker, 'ask'>
  actuator: Actuator
  now?: () => number
  sleep?: (ms: number) => Promise<void>
  // The only localhost origin open_url may reach (our practice stage).
  stageOrigin?: string
  homeDir?: string
  // Seconds since the last keyboard/mouse input (tests inject it; main reads powerMonitor). Absent under tests => treated as active.
  idleSeconds?: () => number
}

export const MAX_AUTO_PER_SESSION = 3
// A step counts as stalled (past the help ladder) after this long without finishing.
export const STALLED_STEP_MS = 90_000
// The ring and ghost cursor are on screen this long before an auto-approved action runs.
export const AUTO_LEAD_MS = 1500

export const sleepMs = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

export const stageOriginFromEnv = (): string => `http://127.0.0.1:${process.env.STAGE_PORT || '5180'}`

// What is going on right now, as far as the policy cares. One subscription per agency instance.
export class Situation {
  safetyCritical = false
  // AUTONOMOUS bookkeeping (main-process state only). One auto action per lesson step, at most MAX_AUTO_PER_SESSION per session.
  lastApproval: 'auto-away' | undefined
  autoOffForSession = false
  autoCount = 0
  private autoStepKey = ''
  private stepKey = ''
  private stepStartedAt = 0
  // Bumped on every session end (Stop included): a task that captured an older value has been stopped.
  epoch = 0
  private readonly off: Array<() => void> = []

  constructor(private readonly ctx: ServiceContext, private readonly clock: () => number = Date.now) {
    this.off.push(
      ctx.bus.on('lesson:step', (e) => {
        const key = `${e.lessonId}:${e.stepIndex}`
        if (e.phase === 'done' || e.phase === 'aborted') this.stepKey = ''
        else if (e.phase === 'started' || key !== this.stepKey) {
          this.stepKey = key
          this.stepStartedAt = this.clock()
        }
        this.safetyCritical = e.phase === 'done' || e.phase === 'aborted' ? false : (e.step?.safetyCritical ?? this.safetyCritical)
      }),
      ctx.bus.on('session:ended', (e) => {
        this.epoch++
        this.safetyCritical = false
        this.stepKey = ''
        // Stop ends autonomous for the rest of the session, and the owner has to switch it on again.
        this.autonomyOff()
        if (e?.reason === 'stop' && (ctx.settings.get() as { agency?: string }).agency === 'autonomous') ctx.settings.patch({ agency: 'ask_each' })
      }),
      ctx.bus.on('session:request', () => {
        this.autoOffForSession = false
        this.autoCount = 0
        this.autoStepKey = ''
      }),
    )
  }

  get scam(): boolean {
    const st = this.ctx.state.get()
    return st.skill?.id === 'spot_scam' || st.agents.some((a) => a.kind === 'scam_check' && a.status === 'running')
  }

  autonomyOff(): void {
    this.autoOffForSession = true
    this.lastApproval = undefined
  }

  // Is a lesson step active and stalled (nothing happened for `stalledMs` since it started, i.e. past the help ladder)?
  stepStalled(nowMs: number, stalledMs: number): boolean {
    return this.stepKey !== '' && nowMs - this.stepStartedAt >= stalledMs
  }

  // Claims the one auto action allowed for the current step; false if already used or the session cap is reached.
  claimAuto(): boolean {
    if (this.autoCount >= MAX_AUTO_PER_SESSION || this.stepKey === '' || this.autoStepKey === this.stepKey) return false
    this.autoStepKey = this.stepKey
    this.autoCount++
    return true
  }

  dispose(): void {
    for (const off of this.off.splice(0)) off()
  }
}

export function policyContext(deps: AgencyDeps, sit: Situation, planApproved: boolean): PolicyContext {
  const settings = deps.ctx.settings.get() as { agency: PolicyContext['agency']; fileFolders?: string[] }
  return {
    agency: settings.agency,
    safetyCriticalStep: sit.safetyCritical,
    scamContext: sit.scam,
    planApproved,
    stageOrigin: deps.stageOrigin ?? stageOriginFromEnv(),
    fileRoots: Array.isArray(settings.fileFolders) ? settings.fileFolders : [],
    homeDir: deps.homeDir ?? os.homedir(),
  }
}

// ---------- wording ----------

const PANE_WORDS: Record<string, string> = {
  displays: 'display',
  'accessibility-display': 'text size and display',
  sound: 'sound',
  wifi: 'Wi-Fi',
  bluetooth: 'Bluetooth',
  notifications: 'notifications',
  keyboard: 'keyboard',
  general: 'general',
}

const clip = (text: string, max: number): string => (text.length > max ? `${text.slice(0, max - 1)}…` : text)

// "www.example.com" for https://www.example.com/path?x=1; never the query (it can hold personal text).
export function hostOf(url: string): string {
  try {
    return new URL(url).host
  } catch {
    return 'that website'
  }
}

export function describeAction(a: ProposedAction): string {
  switch (a.kind) {
    case 'open_url':
      return `open ${hostOf(a.value ?? '')}`
    case 'open_app':
      return `open ${clip((a.value ?? 'that app').trim(), 40)}`
    case 'open_file':
      return `show you where "${clip(path.basename(a.value ?? 'that file'), 40)}" is`
    case 'open_settings': {
      const pane = resolvePane(a.value)
      return `open the ${pane ? PANE_WORDS[pane] : 'settings'} settings`
    }
    case 'click':
      return `click "${clip(a.label ?? 'that', 50)}"`
    case 'double_click':
      return `double-click "${clip(a.label ?? 'that', 50)}"`
    case 'type':
      return `type "${clip(a.text ?? '', 60)}"`
    case 'keys':
      return `press the ${clip(a.value ?? 'key', 20)} key`
    case 'scroll':
      return `scroll ${clip(a.label ?? 'the page', 30)}`
    case 'wait':
      return 'wait a moment'
  }
}

export const isOpenKind = (k: ActionKind): boolean => k === 'open_url' || k === 'open_app' || k === 'open_file' || k === 'open_settings'

export const APPROVE_OPEN = 'Yes, open it'
export const APPROVE_DO = 'Yes, do it'
export const APPROVE_GO = 'Yes, go ahead'
export const DECLINE = 'No, I will'

// ---------- on-screen explanation ----------

export const BUBBLE_ID = 'agency-bubble'
export const RING_ID = 'agency-ring'
export const GHOST_ID = 'agency-ghost'
export const TICK_ID = 'agency-tick'
export const AGENCY_IDS = [BUBBLE_ID, RING_ID, GHOST_ID, TICK_ID]

export const banner = (text: string, ttlMs?: number, tone: Annotation['tone'] = 'guide'): Annotation => ({ id: BUBBLE_ID, kind: 'bubble', tone, at: { x: 500, y: 130 }, text, ...(ttlMs ? { ttlMs } : {}) })

export const centreOf = (b: { xmin: number; ymin: number; xmax: number; ymax: number }): NormPoint => ({ x: (b.xmin + b.xmax) / 2, y: (b.ymin + b.ymax) / 2 })

export function idleFromElectron(): number {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { powerMonitor } = require('electron') as typeof import('electron')
    const n = powerMonitor.getSystemIdleTime()
    return Number.isFinite(n) ? n : 0
  } catch {
    return 0
  }
}

// Away = owner opted in (agency autonomous) AND no keyboard/mouse for awaySeconds AND an active lesson step stalled AND no scam
// check / safety-critical step AND Stop has not been pressed this session. Anything else => the normal approval modal.
export function autonomousAway(deps: AgencyDeps, sit: Situation, checkStalled = true): boolean {
  const s = deps.ctx.settings.get() as { agency: string; awaySeconds?: number }
  if (s.agency !== 'autonomous' || sit.autoOffForSession || sit.scam || sit.safetyCritical) return false
  if (checkStalled && !sit.stepStalled((deps.now ?? Date.now)(), STALLED_STEP_MS)) return false
  const idle = (deps.idleSeconds ?? idleFromElectron)()
  return idle >= Math.max(3, s.awaySeconds ?? 60)
}

export type ConfirmOutcome = 'yes' | 'no' | 'stopped'

// A real-click confirmation: the approval can only come from the dock modal (ConfirmBroker), never from model text.
// One approval buys exactly one action; callers re-check settings and Stop right after this returns.
export async function askToProceed(deps: AgencyDeps, sit: Situation, question: string, approve: string): Promise<ConfirmOutcome> {
  const epoch = sit.epoch
  sit.lastApproval = undefined
  if (autonomousAway(deps, sit)) {
    // The ONE no-click path: decided by main-process state only (owner setting + system idle + stalled lesson step). The caller
    // has already run the policy and drawn the ring/ghost; it re-runs the policy and the actuator right after this returns.
    await (deps.sleep ?? sleepMs)(AUTO_LEAD_MS)
    if (sit.epoch !== epoch) return 'stopped'
    if (autonomousAway(deps, sit, false) && sit.claimAuto()) {
      sit.lastApproval = 'auto-away'
      return 'yes'
    }
  }
  const choice = await deps.confirm.ask(question, [approve, DECLINE])
  if (sit.epoch !== epoch) return 'stopped'
  return choice === approve ? 'yes' : 'no'
}

// Never lets an overlay or audit failure break the task.
export function safely(ctx: ServiceContext, what: string, fn: () => void): void {
  try {
    fn()
  } catch (err) {
    ctx.log('agency', `${what} failed:`, err instanceof Error ? err.message : err)
  }
}
