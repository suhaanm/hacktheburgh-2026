// open_for_me{kind:'url'|'app'|'file'|'settings', value}: Tier 1. One action, no screenshot, no Accessibility.
// Flow: agency setting -> policy (URL/app/file/pane rules, scam + safety-critical refusals) -> a bubble on screen saying what
// is about to happen -> a real-click confirmation (every time, in both ask_each and ask_per_task: one action IS the plan)
// -> the Actuator -> a short result. Audited. The result text tells the model to narrate and offer to teach next time.
import type { AgencyCode, AgencyResult } from '../../shared/protocol'
import type { ActResult } from '../actuator'
import { appendAgencyAudit } from './audit'
import {
  AGENCY_IDS,
  APPROVE_OPEN,
  askToProceed,
  banner,
  describeAction,
  hostOf,
  policyContext,
  safely,
  sleepMs,
  type AgencyDeps,
  type Situation,
} from './common'
import { evaluateAction, resolvePane, type ActionLimiter, type ProposedAction } from './policy'

export type OpenKind = 'url' | 'app' | 'file' | 'settings'
export interface OpenArgs {
  kind: OpenKind
  value: string
}

export type DoneForMeSink = (key: string) => void | Promise<void>

const RESULT_MS = 4000

function proposal(args: OpenArgs): ProposedAction {
  switch (args.kind) {
    case 'url':
      return { kind: 'open_url', value: args.value.trim() }
    case 'app':
      return { kind: 'open_app', value: args.value.trim() }
    case 'file':
      return { kind: 'open_file', value: args.value.trim() }
    case 'settings':
      return { kind: 'open_settings', value: args.value.trim() }
  }
}

const auditHost = (a: ProposedAction): string | undefined => (a.kind === 'open_url' ? hostOf(a.value ?? '') : undefined)
const auditLabel = (a: ProposedAction): string => (a.kind === 'open_url' ? 'website' : a.kind === 'open_app' ? (a.value ?? 'app') : a.kind === 'open_file' ? 'file' : `settings:${resolvePane(a.value) ?? 'unknown'}`)

export function createOpenForMe(deps: AgencyDeps, sit: Situation, limiter: ActionLimiter, doneForMe: DoneForMeSink): (args: OpenArgs) => Promise<AgencyResult> {
  const { ctx, s, actuator } = deps
  const now = deps.now ?? Date.now
  const sleep = deps.sleep ?? sleepMs

  const audit = async (a: ProposedAction, decision: 'allowed' | 'blocked' | 'declined' | 'stopped' | 'refused', ok: boolean, code: string, dryRun?: boolean): Promise<void> => {
    try {
      await appendAgencyAudit(ctx.userDataDir, { tool: 'open_for_me', decision, ok, code, label: auditLabel(a), host: auditHost(a), dryRun, ...(decision === 'allowed' && sit.lastApproval ? { approval: sit.lastApproval } : {}) }, now)
    } catch (err) {
      ctx.log('agency', 'audit write failed:', err instanceof Error ? err.message : err)
    }
  }

  const result = (code: AgencyCode, allowed: boolean, done: boolean, reason: string, extra: Partial<AgencyResult> = {}): AgencyResult => ({ allowed, done, code, reason, ...extra })

  const perform = async (a: ProposedAction): Promise<ActResult> => {
    switch (a.kind) {
      case 'open_url':
        return actuator.openUrl(a.value ?? '')
      case 'open_app':
        return actuator.openApp(a.value ?? '')
      case 'open_file':
        return actuator.revealPath(a.value ?? '')
      case 'open_settings': {
        const pane = resolvePane(a.value)
        if (!pane) return { ok: false, reason: 'blocked', detail: 'unknown pane' }
        const r = await actuator.openSettingsPane(pane)
        // A pane link that macOS does not know still gets the learner into Settings.
        return r.ok || r.reason === 'blocked' ? r : actuator.openApp('System Settings')
      }
      default:
        return { ok: false, reason: 'blocked', detail: 'not an open action' }
    }
  }

  return async (args) => {
    let action = proposal(args)
    // A file is revealed only if the FILES index vouches for it (indexed, inside a consented folder, files switched on):
    // the model's own string is never trusted, and the real path is what the Actuator gets.
    if (action.kind === 'open_file' && deps.s.files) {
      const real = deps.s.files.resolveIndexedPath(action.value ?? '')
      if (!real) {
        await audit(action, 'blocked', false, 'blocked')
        return result('blocked', false, false, 'I can only open files you let me look at. Show the learner where to look instead.')
      }
      action = { ...action, value: real }
    }
    const decision = evaluateAction(action, policyContext(deps, sit, false))
    if (!decision.allowed) {
      await audit(action, decision.code === 'agency_off' ? 'refused' : 'blocked', false, decision.code)
      return result(decision.code, false, false, decision.reason)
    }

    const what = describeAction(action)
    const insecure = decision.flags.includes('http_not_https') ? ' That website is not a secure one.' : ''
    safely(ctx, 'overlay', () => s.overlay.show([banner(`I'm about to ${what}.`, 30_000)]))

    const outcome = await askToProceed(deps, sit, `I'll ${what} for you. OK?${insecure}`, APPROVE_OPEN)
    if (outcome !== 'yes') {
      safely(ctx, 'overlay', () => s.overlay.clear(AGENCY_IDS))
      const stopped = outcome === 'stopped'
      await audit(action, stopped ? 'stopped' : 'declined', false, stopped ? 'stopped' : 'declined')
      return stopped
        ? result('stopped', true, false, 'Stop was pressed, so nothing was opened.')
        : result('declined', true, false, 'The learner did not approve. Let them do it, and show them how if they want.')
    }

    // One approval buys exactly one action; settings and policy are re-read because they can change while the modal waits.
    const again = evaluateAction(action, policyContext(deps, sit, false))
    if (!again.allowed) {
      safely(ctx, 'overlay', () => s.overlay.clear(AGENCY_IDS))
      await audit(action, 'refused', false, again.code)
      return result(again.code, false, false, again.reason)
    }
    for (let tries = 0; tries < 3; tries++) {
      const slot = limiter.take(now())
      if (slot.ok) break
      if (slot.why !== 'gap' || tries === 2) {
        safely(ctx, 'overlay', () => s.overlay.clear(AGENCY_IDS))
        await audit(action, 'refused', false, 'rate_limited')
        return result('rate_limited', true, false, 'That was too many things too quickly, so nothing was opened. Wait a moment, then offer to try again.')
      }
      await sleep(slot.waitMs)
    }

    const r = await perform(action)
    safely(ctx, 'overlay', () => s.overlay.clear(AGENCY_IDS))
    const label = action.kind === 'open_url' ? hostOf(action.value ?? '') : what.replace(/^open /, '')
    if (!r.ok) {
      const code: AgencyCode = r.reason === 'blocked' ? 'blocked' : 'failed'
      await audit(action, 'allowed', false, code)
      return result(code, true, false, r.reason === 'blocked' ? `That could not be opened (${r.detail ?? 'not allowed'}). Show the learner how instead.` : 'That did not open: it may not be installed, or the computer refused. Show the learner how instead.', { label })
    }
    const dryRun = r.reason === 'dry-run'
    safely(ctx, 'overlay', () => s.overlay.show([banner(`Opened ${label}.`, RESULT_MS, 'success')]))
    await audit(action, 'allowed', true, 'done', dryRun)
    if (!dryRun) {
      const key = ctx.state.get().skill?.id ?? `open:${action.kind === 'open_url' ? label : action.kind}`
      try {
        await doneForMe(key)
      } catch (err) {
        ctx.log('agency', 'doneForMe count failed:', err instanceof Error ? err.message : err)
      }
    }
    return result(
      'done',
      true,
      true,
      dryRun
        ? `Dry run: opening ${label} was logged, not performed.`
        : `Opened ${label} for the learner. Now say in one short sentence what you did, and offer to show them how to do it themselves next time.`,
      { label, dryRun },
    )
  }
}

