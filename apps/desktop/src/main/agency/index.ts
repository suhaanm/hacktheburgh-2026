// AGENCY: what the assistant may DO for a learner, always under their control. See docs/AGENCY.md.
// createAgency() is built once by the dispatcher; DEMO and the debug server reach it through getAgency().
import type { AgencyResult } from '../../shared/protocol'
import { geminiDeps } from '../gemini'
import { createActForMe, type ActOptions } from './act-for-me'
import { createAxResolver } from './ax-resolver'
import { Situation, type AgencyDeps } from './common'
import { createOpenForMe, type DoneForMeSink, type OpenArgs } from './open-for-me'
import { readFocusInfo, readFrontApp } from './scope'
import { ActionLimiter } from './policy'

export { lastAuditLine, appendAgencyAudit } from './audit'
export { evaluateAction, evaluateGoal, checkUrl, ActionLimiter } from './policy'
export type { OpenArgs } from './open-for-me'

export interface Agency {
  // Programmatic entry points (no Live model needed): same policy, same real-click confirmation, same audit.
  runOpenForMe(args: OpenArgs): Promise<AgencyResult>
  runActForMe(goal: string): Promise<AgencyResult>
  // Ends a running act_for_me at its next check (also happens on session:ended / the Stop button).
  stop(): void
  dispose(): void
}

// ON by default (user decision 15:46); ALONGSIDE_AGENCY_LOOP=0 switches the multi-step loop off. It still needs agency != 'off' and
// every action passes the policy engine and the confirmation gate.
export const agencyLoopFromEnv = (): boolean => process.env.ALONGSIDE_AGENCY_LOOP !== '0'

export function createAgency(deps: AgencyDeps & { act?: Partial<ActOptions> }): Agency {
  const sit = new Situation(deps.ctx, deps.now)
  const doneForMe: DoneForMeSink = (key) => deps.s.learner.recordDoneForMe?.(key)
  // One limiter for stand-alone opens: >= 1.5 s apart, at most 12 a minute. act_for_me has its own per-task limiter.
  const openLimiter = new ActionLimiter(1_000_000, 1500, 12)
  const open = createOpenForMe(deps, sit, openLimiter, doneForMe)
  const act = createActForMe(deps, sit, doneForMe, {
    gemini: () => geminiDeps(deps.ctx, { capture: deps.s.capture }),
    loopEnabled: agencyLoopFromEnv,
    cursor: cursorFromElectron,
    // Accessibility-first targets for native apps (exact element frames); off under unit tests, ALONGSIDE_AX_RESOLVER=0 disables it.
    ...(process.env.VITEST ? {} : { resolveAx: createAxResolver({ log: deps.ctx.log }) }),
    // Scope: the frontmost app is read (name only, via lsappinfo) before every action; ALONGSIDE_AGENCY_SCOPE=0 disables it.
    ...(process.env.VITEST || process.env.ALONGSIDE_AGENCY_SCOPE === '0' ? {} : { frontApp: readFrontApp, focusInfo: readFocusInfo }),
    ...deps.act,
  })
  return {
    runOpenForMe: open,
    runActForMe: (goal) => act.run(goal),
    stop: () => act.stop(),
    dispose: () => sit.dispose(),
  }
}

// The pointer position as a NormPoint on the primary display; electron is imported lazily so tests need none.
function cursorFromElectron(): { x: number; y: number } | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { screen } = require('electron') as typeof import('electron')
    const p = screen.getCursorScreenPoint()
    const b = screen.getPrimaryDisplay().bounds
    if (!b.width || !b.height) return null
    return { x: Math.min(1000, Math.max(0, ((p.x - b.x) / b.width) * 1000)), y: Math.min(1000, Math.max(0, ((p.y - b.y) / b.height) * 1000)) }
  } catch {
    return null
  }
}

let current: Agency | null = null
export const setAgency = (a: Agency | null): void => {
  current = a
}
export const getAgency = (): Agency | null => current
