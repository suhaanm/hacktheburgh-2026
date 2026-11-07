// act_for_me{goal}: a short multi-step task on Gemini's computer_use tool, under the learner's control.
// Loop discipline (our own, written from the principles in research/02, not from any other codebase):
//   - a mutation only ever follows a FRESH screen read; every step is one model call on one fresh screenshot
//   - the model proposes ONE action; our policy decides, never the model's words; the action is shown on screen
//     (ring + ghost-cursor path + a plain sentence) BEFORE it runs, and confirmed with a real click per settings.agency
//   - a failed action is never retried; the same action id is never run twice (the model is told so and gets up to 2 recoveries
//     to pick another step); a click on the same element is never made more than twice
//   - no visible effect: a short wait and a second look, then ONE re-plan with feedback; a second miss in a row ends the task
//   - typed text that does not show on screen is retried once by clipboard paste (the clipboard is restored)
//   - success is claimed only when the Verifier confirms the goal on a fresh screenshot
//   - the goal text the learner gave is the only task; screen text is data (see computer-use.ts)
//   - scope: the frontmost app is read before every action; another app (or Claude / a terminal) coming to the front stops the task
//   - at most 12 actions, 120 s in total, Stop (session:ended) ends it at the next check and nothing is left half-done
// Without macOS Accessibility the loop never acts: it rings the target and tells the learner what to click.
import { createHash } from 'node:crypto'
import type { AgentChip, AgencyCode, AgencyResult, Annotation, NormPoint, Shot } from '../../shared/protocol'
import { plainFailure, type GeminiDeps } from '../gemini/client'
import { boxAroundPoint } from '../gemini/grounding-utils'
import type { ActResult } from '../actuator'
import { appendAgencyAudit, type AgencyAuditEntry } from './audit'
import {
  AGENCY_IDS,
  APPROVE_DO,
  APPROVE_GO,
  askToProceed,
  banner,
  describeAction,
  GHOST_ID,
  policyContext,
  RING_ID,
  safely,
  sleepMs,
  TICK_ID,
  type AgencyDeps,
  type Situation,
} from './common'
import type { AxResolve } from './ax-resolver'
import { proposeNext, type Proposal, type ProposeRequest, type ProposedStep } from './computer-use'
import { ActionLimiter, evaluateAction, evaluateGoal, goalAcceptsCookies, MAX_ACTIONS_PER_TASK, normaliseKeys, riskWords, stripNegatedClauses, type ProposedAction, type ReturnFacts } from './policy'
import type { DoneForMeSink } from './open-for-me'
import { checkScope, isBrowser, isOwnApp, scopeFromGoal, type FrontApp, type ReadFocus, type ScopeState } from './scope'

export const MAX_TASK_MS = 120_000
// The model asking for an already-run step again: it is told, and may pick another step this many times per task.
export const MAX_REPEAT_RECOVERIES = 2
// A click on the same element is never made more than this many times in one task.
export const MAX_CLICKS_PER_ELEMENT = 2
// Short pause between clicking a field and typing into it, so focus has settled.
const FOCUS_SETTLE_MS = 350
const PROPOSE_MS = 25_000
const SETTLE_MS = 900
const GHOST_TTL_MS = 20_000
const CHIP_TITLE = 'Doing this for you'

export interface ActOptions {
  gemini: () => GeminiDeps
  // ALONGSIDE_AGENCY_LOOP=0 switches the loop off (it is on by default).
  loopEnabled: () => boolean
  maxSteps?: number
  totalMs?: number
  settleMs?: number
  // Test seam: replaces the real model call.
  propose?: (req: ProposeRequest) => Promise<Proposal>
  // Where the pointer is now (normalised); the ghost cursor starts there.
  cursor?: () => NormPoint | null
  // Accessibility-first resolver: re-run right before each click/double-click; null = keep the vision coordinates.
  resolveAx?: AxResolve
  // Frontmost application name (scope enforcement); absent or null = unknown, never blocks.
  frontApp?: FrontApp
  // Focused-element / window-title read for the narrow Return allowance; absent = it cannot tell, so Return stays blocked.
  focusInfo?: ReadFocus
}

const hashOf = (shot: Shot): string => createHash('sha1').update(shot.jpegBase64).digest('hex')
const oneLine = (text: string, max = 200): string => text.replace(/\s+/g, ' ').trim().slice(0, max)

// A gentle arc from the pointer to the target so the learner can follow the movement with their eyes.
export function ghostPath(from: NormPoint | null, to: NormPoint): NormPoint[] {
  const start = from ?? { x: Math.max(0, to.x - 160), y: Math.min(1000, to.y + 140) }
  const mid = { x: (start.x + to.x) / 2, y: Math.max(0, Math.min(start.y, to.y) - 60) }
  return [start, mid, to]
}

function toProposed(step: ProposedStep): ProposedAction {
  switch (step.tool) {
    case 'click':
      return { kind: 'click', label: step.intent, targetText: step.safety?.explanation }
    case 'double_click':
      return { kind: 'double_click', label: step.intent, targetText: step.safety?.explanation }
    case 'type':
      return { kind: 'type', label: step.intent, text: step.text, targetText: step.safety?.explanation }
    case 'keys':
      return { kind: 'keys', label: step.intent, value: step.keys, targetText: step.safety?.explanation }
    case 'scroll':
      return { kind: 'scroll', label: step.intent }
    case 'wait':
      return { kind: 'wait', label: step.intent }
  }
}

// What the learner reads: the model's own words for the target when it gave some, else a plain default.
function say(step: ProposedStep): string {
  const intent = oneLine(step.intent, 90)
  switch (step.tool) {
    case 'type':
      return `type "${oneLine(step.text ?? '', 50)}"`
    case 'keys':
      return `press the ${oneLine(step.keys ?? 'key', 20)} key`
    case 'scroll':
      return `scroll ${(step.dy ?? 0) < 0 ? 'up' : 'down'}`
    case 'wait':
      return 'wait a moment'
    default:
      return intent ? intent.charAt(0).toLowerCase() + intent.slice(1).replace(/[.!]+$/, '') : step.tool === 'double_click' ? 'double-click here' : 'click here'
  }
}

export interface ActForMe {
  run(goal: string): Promise<AgencyResult>
  stop(): void
  isRunning(): boolean
}

export function createActForMe(deps: AgencyDeps, sit: Situation, doneForMe: DoneForMeSink, opts: ActOptions): ActForMe {
  const { ctx, s, actuator } = deps
  const now = deps.now ?? Date.now
  const sleep = deps.sleep ?? sleepMs
  const maxSteps = opts.maxSteps ?? MAX_ACTIONS_PER_TASK
  const totalMs = opts.totalMs ?? MAX_TASK_MS
  const settleMs = opts.settleMs ?? SETTLE_MS
  const propose = opts.propose ?? ((req) => proposeNext(opts.gemini(), req))
  let active: { epoch: number; chipId: string } | null = null
  let chipSeq = 0
  // The frontmost app as last read (name only), written into every audit line of the task.
  let frontNow: string | undefined

  const audit = async (entry: Omit<AgencyAuditEntry, 'tool'>): Promise<void> => {
    try {
      await appendAgencyAudit(ctx.userDataDir, { tool: 'act_for_me', ...(frontNow ? { app: frontNow } : {}), ...entry, ...(entry.decision === 'allowed' && sit.lastApproval ? { approval: sit.lastApproval } : {}) }, now)
    } catch (err) {
      ctx.log('agency', 'audit write failed:', err instanceof Error ? err.message : err)
    }
  }
  const result = (code: AgencyCode, allowed: boolean, done: boolean, reason: string, extra: Partial<AgencyResult> = {}): AgencyResult => ({ allowed, done, code, reason, ...extra })

  // ---------- the chip in the agent tray ----------
  let chip: AgentChip | null = null
  const publishChip = (patch: Partial<AgentChip>): void => {
    if (!chip) return
    chip = { ...chip, ...patch }
    safely(ctx, 'chip', () => {
      ctx.state.upsertAgent(chip as AgentChip)
      ctx.bus.emit('agent:update', { chip: { ...(chip as AgentChip) } })
    })
  }
  // The agent runtime republishes its own chip list and would drop ours: put it back.
  ctx.state.subscribe?.((st) => {
    if (chip && active && !st.agents.some((a) => a.id === chip?.id)) safely(ctx, 'chip', () => ctx.state.upsertAgent(chip as AgentChip))
  })

  const clearScreen = (): void => safely(ctx, 'overlay', () => s.overlay.clear(AGENCY_IDS))

  async function run(goal: string): Promise<AgencyResult> {
    const task = oneLine(goal, 300)
    const goalDecision = evaluateGoal(task, policyContext(deps, sit, false))
    if (!goalDecision.allowed) {
      await audit({ decision: goalDecision.code === 'agency_off' ? 'refused' : 'blocked', ok: false, code: goalDecision.code, label: 'task' })
      return result(goalDecision.code, false, false, goalDecision.reason)
    }
    if (!opts.loopEnabled()) {
      await audit({ decision: 'unavailable', ok: false, code: 'unavailable', label: 'task' })
      return result('unavailable', false, false, 'Doing multi-step tasks is not switched on in this build. Teach the learner step by step instead, or use open_for_me to open a website or app.')
    }
    if (active) return result('busy', false, false, 'Another task is already running. Wait for it to finish or for the learner to press Stop.')

    const epoch = sit.epoch
    active = { epoch, chipId: `act-${now()}-${++chipSeq}` }
    chip = { id: active.chipId, kind: 'lookup', title: CHIP_TITLE, status: 'running', startedAt: now(), summary: 'Getting ready' }
    publishChip({})
    const stopped = (): boolean => sit.epoch !== epoch
    try {
      const out = await loop(task, stopped)
      publishChip({ status: out.done ? 'done' : out.code === 'stopped' || out.code === 'declined' ? 'cancelled' : 'error', summary: oneLine(out.reason, 120) })
      return out
    } catch (err) {
      ctx.log('agency', 'act_for_me failed:', err instanceof Error ? err.message : err)
      publishChip({ status: 'error', summary: 'I could not finish that' })
      await audit({ decision: 'allowed', ok: false, code: 'failed', label: 'task' })
      return result('failed', true, false, 'Something went wrong, so I stopped. Nothing was retried. Show the learner how to do it instead.')
    } finally {
      clearScreen()
      active = null
    }
  }

  async function loop(task: string, stopped: () => boolean): Promise<AgencyResult> {
    const started = now()
    const mode = ctx.settings.get().agency
    const status = actuator.status()
    const canAct = status.dryRun || status.accessibility
    const history: string[] = []
    const seen = new Set<string>()
    const limiter = new ActionLimiter(maxSteps)
    const scopeState: ScopeState = { scope: scopeFromGoal(task) }
    frontNow = undefined
    const clicksOn = new Map<string, number>()
    const acceptsCookies = goalAcceptsCookies(task)
    let repeatRecoveries = 0
    let feedback: string | undefined
    let lastNote = 'nothing has been done yet'
    // Before every action: is the frontmost app still the one this task is about? null = fine, else the stopping result.
    const checkFront = async (steps: number): Promise<AgencyResult | null> => {
      if (!opts.frontApp) return null
      let name: string | null = null
      try {
        name = await opts.frontApp()
      } catch {
        name = null
      }
      if (name) frontNow = name
      const verdict = checkScope(scopeState, name)
      if (verdict.ok) return null
      clearScreen()
      await audit({ decision: 'blocked', ok: false, code: 'blocked', label: 'scope', step: steps })
      return result('blocked', false, false, `${verdict.message} Steps done so far: ${steps}.`, { steps })
    }
    // The model asked for a step that already ran (or a third click on one element): tell it, do not stop yet.
    const recoverRepeat = async (what: string, steps: number): Promise<AgencyResult | null> => {
      repeatRecoveries++
      if (repeatRecoveries > MAX_REPEAT_RECOVERIES) {
        await audit({ decision: 'blocked', ok: false, code: 'gave_up', label: 'repeat', step: steps })
        return result('gave_up', true, false, 'The helper kept asking for the same step, so I stopped instead of repeating it. Show the learner instead.', { steps })
      }
      feedback = `You already did "${oneLine(what, 80)}"; ${lastNote}; choose a DIFFERENT next step or finish.`
      history.push(`(asked for "${oneLine(what, 110)}" again: not repeated)`)
      await audit({ decision: 'allowed', ok: false, code: 'repeat', label: `recovery ${repeatRecoveries}`, step: steps })
      return null
    }
    const stopResult = async (done: number): Promise<AgencyResult> => {
      clearScreen()
      await audit({ decision: 'stopped', ok: false, code: 'stopped', label: 'task', step: done })
      return result('stopped', true, false, 'Stop was pressed, so the task ended right there. Nothing was left half-done.', { steps: done })
    }

    // Scope: record the frontmost app BEFORE any prompt takes the focus (the verdict is only used before actions, not here).
    if (opts.frontApp) {
      try {
        const name = await opts.frontApp()
        if (name) {
          frontNow = name
          checkScope(scopeState, name)
        }
      } catch {
        // unreadable: scope checks stay lenient
      }
    }

    // ask_per_task: the learner confirms the plan (their own goal) once. ask_each skips this and confirms every action.
    let planApproved = false
    if (mode === 'ask_per_task' && canAct) {
      safely(ctx, 'overlay', () => s.overlay.show([banner(`I'd like to: ${oneLine(task, 120)}`, 60_000)]))
      const plan = await askToProceed(deps, sit, `I'll try to: ${oneLine(task, 160)}. I'll check with you before anything risky. OK?`, APPROVE_GO)
      clearScreen()
      if (plan === 'stopped') return stopResult(0)
      if (plan === 'no') {
        await audit({ decision: 'declined', ok: false, code: 'declined', label: 'task' })
        return result('declined', true, false, 'The learner did not approve. Let them do it, and show them how if they want.')
      }
      planApproved = true
    }

    // The narrow Return allowance: what the immediately preceding executed action was, and how many Returns were pressed.
    let prevTyped: string | null = null
    let returnsDone = 0
    let carry: Shot | null = null
    let done = 0
    let unchanged = 0
    let prevWasClick = false
    // Recoveries (repeat feedback, one re-plan) cost a model call but no action: they get their own headroom.
    for (let n = 1; n <= maxSteps + 1 + MAX_REPEAT_RECOVERIES + 2; n++) {
      if (stopped()) return stopResult(done)
      if (now() - started > totalMs) {
        await audit({ decision: 'allowed', ok: false, code: 'gave_up', label: 'timeout', step: done })
        return result('gave_up', true, false, `That took longer than ${Math.round(totalMs / 1000)} seconds, so I stopped. Nothing was retried. Show the learner the rest.`, { steps: done })
      }
      publishChip({ summary: done === 0 ? 'Looking at your screen' : `Step ${done} done. Looking again` })

      // A mutation only ever follows a fresh read: reuse the post-action capture only when it is a moment old.
      const fresh = carry && now() - carry.takenAt < 2500 ? carry : await s.capture.grab('ground')
      carry = null
      if (stopped()) return stopResult(done)
      const outOfScope = await checkFront(done)
      if (outOfScope) return outOfScope

      let proposal: Proposal
      try {
        const note = feedback
        feedback = undefined
        proposal = await propose({ goal: task, history, shot: fresh, timeoutMs: Math.max(3000, Math.min(PROPOSE_MS, totalMs - (now() - started))), ...(note ? { feedback: note } : {}) })
      } catch (err) {
        await audit({ decision: 'allowed', ok: false, code: 'failed', label: 'model', step: done })
        return result('failed', true, false, `${plainFailure(err)} Nothing was changed. Show the learner how to do it instead.`, { steps: done })
      }
      if (stopped()) return stopResult(done)

      if (proposal.kind === 'finished') return finish(task, proposal.text, done)
      if (proposal.kind === 'unsupported') {
        await audit({ decision: 'blocked', ok: false, code: 'gave_up', label: proposal.name, step: done })
        return result('gave_up', true, false, 'The helper wanted to do something I do not do, so I stopped. Show the learner how instead.', { steps: done })
      }
      if (proposal.kind === 'blocked') {
        await audit({ decision: 'blocked', ok: false, code: 'blocked', label: 'safety', step: done })
        return result('blocked', false, false, `The safety check stopped this step: ${oneLine(proposal.reason, 160)} Show the learner instead.`, { steps: done })
      }
      if (done >= maxSteps) {
        await audit({ decision: 'allowed', ok: false, code: 'gave_up', label: 'step limit', step: done })
        return result('gave_up', true, false, `I stopped after ${maxSteps} steps and did not finish. Show the learner the rest.`, { steps: done })
      }

      const step = proposal.step
      if (step.tool === 'wait') {
        history.push('waited a moment')
        await sleep(Math.min(5, step.seconds ?? 1) * 1000)
        done++
        continue
      }
      // The same request is never run twice, even if the screen looks the same: the model must find another way.
      if (seen.has(step.id)) {
        const stop = await recoverRepeat(say(step), done)
        if (stop) return stop
        continue
      }
      seen.add(step.id)

      const action = toProposed(step)
      // Return is judged on facts read now (front app, window title, focused field), once per step and reused after any prompt.
      let returnFacts: ReturnFacts | undefined
      if (step.tool === 'keys' && ['return', 'enter'].includes(normaliseKeys(step.keys ?? ''))) {
        let front: string | null = null
        let focus: { secure: boolean | null; title: string | null } = { secure: null, title: null }
        try {
          front = opts.frontApp ? await opts.frontApp() : null
          if (opts.focusInfo) focus = await opts.focusInfo()
        } catch {
          // unreadable: Return stays blocked
        }
        const target = scopeState.target ?? null
        returnFacts = {
          prevTypedText: prevTyped,
          returnsSoFar: returnsDone,
          secureField: focus.secure,
          windowTitle: focus.title,
          frontApp: front,
          targetApp: target,
          targetKnown: target !== null && (isBrowser(target) || scopeState.scope.kind === 'app'),
          goalClean: riskWords(stripNegatedClauses(task)) === null,
        }
      }
      const policyNow = (): ReturnType<typeof policyContext> => ({ ...policyContext(deps, sit, planApproved), ...(acceptsCookies ? { goalAcceptsCookies: true } : {}), ...(returnFacts ? { returnFacts } : {}) })
      const decision = evaluateAction(action, policyNow())
      const spot = step.point
      const what = say(step)
      const annotations: Annotation[] = []
      if (spot) {
        annotations.push({ id: RING_ID, kind: 'ring', tone: 'guide', box: boxAroundPoint(spot, 30), label: oneLine(what, 40), ttlMs: GHOST_TTL_MS })
        annotations.push({ id: GHOST_ID, kind: 'ghostCursor', tone: 'guide', path: ghostPath(opts.cursor?.() ?? null, spot), ttlMs: GHOST_TTL_MS })
      }
      if (!decision.allowed) {
        annotations.push(banner('I will leave this one to you.', 12_000, 'warn'))
        safely(ctx, 'overlay', () => s.overlay.show(annotations))
        await audit({ decision: decision.code === 'agency_off' ? 'refused' : 'blocked', ok: false, code: decision.code, label: oneLine(action.kind, 20), step: done })
        return result(decision.code, false, false, `Blocked: "${oneLine(what, 60)}". ${decision.reason} Steps done so far: ${done}. Next: point at it so the learner can do that one step, and offer to carry on afterwards.`, { steps: done, label: oneLine(what, 60) })
      }

      annotations.push(banner(`I'm going to ${what}.`, GHOST_TTL_MS))
      safely(ctx, 'overlay', () => s.overlay.show(annotations)) // shown BEFORE the action runs
      publishChip({ summary: `About to ${oneLine(what, 60)}` })

      if (!canAct) {
        // Guidance only: no Accessibility, so the learner clicks. The ring and the sentence stay up for them.
        await audit({ decision: 'allowed', ok: false, code: 'accessibility', label: oneLine(action.kind, 20), step: done })
        return result('accessibility', true, false, `I cannot click for the learner yet because the computer has not given me the Accessibility permission. I have shown them where to act: "${oneLine(what, 80)}". Tell them in plain words to do that step, and offer to look again afterwards.`, { steps: done, label: oneLine(what, 60) })
      }

      const wantsConfirm = decision.ask || step.safety?.decision === 'require_confirmation'
      if (wantsConfirm) {
        const why = step.safety?.decision === 'require_confirmation' && step.safety.explanation ? ` (${oneLine(step.safety.explanation, 100)})` : ''
        const outcome = await askToProceed(deps, sit, `I'll ${what}${why}. OK?`, APPROVE_DO)
        if (outcome === 'stopped') return stopResult(done)
        if (outcome === 'no') {
          clearScreen()
          await audit({ decision: 'declined', ok: false, code: 'declined', label: oneLine(action.kind, 20), step: done })
          return result('declined', true, false, `The learner said no, so I stopped after ${done} step${done === 1 ? '' : 's'}. Let them do it, and show them how if they want.`, { steps: done })
        }
      }
      // Settings can change and Stop can land while a modal waits: re-check both, then spend the approval on this one action.
      if (stopped()) return stopResult(done)
      const recheck = evaluateAction(action, policyNow())
      if (!recheck.allowed) {
        clearScreen()
        await audit({ decision: 'refused', ok: false, code: recheck.code, label: oneLine(action.kind, 20), step: done })
        return result(recheck.code, false, false, recheck.reason, { steps: done })
      }
      // Re-ground right before the click: the model's coordinates (0-999 on a whole-screen shot) are only good to about
      // +-20 points, more than half a calculator key. Ask Accessibility for the exact frame of the thing the model named.
      let target: ProposedStep = step
      let axKey: string | undefined
      if (opts.resolveAx && step.point && (step.tool === 'click' || step.tool === 'double_click')) {
        const ax = await opts.resolveAx(`${step.intent} ${step.safety?.explanation ?? ''}`.trim(), step.point)
        if (ax) {
          // The denylist and policy apply to the words of the element that will really be hit, too.
          const axAction: ProposedAction = { ...action, targetText: [action.targetText, ax.text].filter(Boolean).join(' ') }
          const axDecision = evaluateAction(axAction, policyNow())
          if (!axDecision.allowed) {
            clearScreen()
            await audit({ decision: 'blocked', ok: false, code: axDecision.code, label: oneLine(action.kind, 20), step: done })
            return result(axDecision.code, false, false, `${axDecision.reason} Steps done so far: ${done}.`, { steps: done, label: oneLine(ax.text, 60) })
          }
          target = { ...step, point: ax.point }
          axKey = `ax:${oneLine(ax.text, 60).toLowerCase()}`
          safely(ctx, 'overlay', () => s.overlay.show([{ id: RING_ID, kind: 'ring', tone: 'guide', box: boxAroundPoint(ax.point, 30), label: oneLine(what, 40), ttlMs: GHOST_TTL_MS }]))
        }
      }
      // The confirmation prompt may have taken the focus (and a different app may have come up): check the scope again, and
      // before typing or pressing keys bring the target app back, otherwise the keystrokes land in Alongside itself.
      const stillInScope = await checkFront(done)
      if (stillInScope) return stillInScope
      const refocusApp = scopeState.target ?? (scopeState.scope.kind === 'app' ? scopeState.scope.app : undefined)
      if ((step.tool === 'type' || step.tool === 'keys') && opts.frontApp && refocusApp && !actuator.status().dryRun) {
        let cur: string | null = null
        try {
          cur = await opts.frontApp()
        } catch {
          cur = null
        }
        if (cur && isOwnApp(cur)) {
          await actuator.openApp(refocusApp)
          await sleep(400)
          const back = await checkFront(done)
          if (back) return back
        }
      }
      // One element is never clicked more than twice: the AX element's words when known, else the screen cell it sits in.
      if (step.tool === 'click' || step.tool === 'double_click') {
        const key = axKey ?? (target.point ? `pt:${Math.round(target.point.x / 40)}:${Math.round(target.point.y / 40)}` : '')
        if (key && (clicksOn.get(key) ?? 0) >= MAX_CLICKS_PER_ELEMENT) {
          const stop = await recoverRepeat(`${say(step)} (that element was already clicked twice)`, done)
          if (stop) return stop
          clearScreen()
          continue
        }
        if (key) clicksOn.set(key, (clicksOn.get(key) ?? 0) + 1)
      }
      if (step.tool === 'type' && prevWasClick) await sleep(FOCUS_SETTLE_MS)
      for (let tries = 0; ; tries++) {
        const slot = limiter.take(now())
        if (slot.ok) break
        if (slot.why !== 'gap' || tries > 3) {
          clearScreen()
          await audit({ decision: 'refused', ok: false, code: 'rate_limited', label: 'limit', step: done })
          return result('rate_limited', true, false, 'That was too many actions too quickly, so I stopped. Show the learner the rest.', { steps: done })
        }
        await sleep(slot.waitMs)
        if (stopped()) return stopResult(done)
      }

      const r = await perform(target)
      prevWasClick = step.tool === 'click' || step.tool === 'double_click'
      if (!r.ok) {
        clearScreen()
        const noAx = r.reason === 'accessibility'
        await audit({ decision: 'allowed', ok: false, code: noAx ? 'accessibility' : 'failed', label: oneLine(action.kind, 20), step: done })
        return result(noAx ? 'accessibility' : 'failed', true, false, noAx ? 'The Accessibility permission is missing, so nothing was done. Show the learner where to act.' : 'That action did not go through, so I stopped and did not retry. Show the learner how instead.', { steps: done })
      }
      done++
      prevTyped = step.tool === 'type' ? (step.text ?? null) : null
      // New text in the field changes what a key press does: Return may be asked for again (still capped by the policy).
      if (step.tool === 'type') for (const id of [...seen]) if (id.startsWith('keys:')) seen.delete(id)
      const returnAfterType = decision.flags.includes('return-after-type')
      if (returnAfterType) returnsDone++
      await audit({ decision: 'allowed', ok: true, code: 'step', label: returnAfterType ? 'keys: return-after-type' : oneLine(`${action.kind}: ${action.kind === 'type' ? 'text' : what}`, 60), step: done, dryRun: r.reason === 'dry-run' })

      if (r.reason === 'dry-run') {
        history.push(`${what} (dry run, nothing happened)`)
        safely(ctx, 'overlay', () => s.overlay.clear([GHOST_ID, RING_ID]))
        continue
      }

      // Settle, then read the screen again: did anything change?
      await sleep(settleMs)
      safely(ctx, 'overlay', () => s.overlay.clear([GHOST_ID, RING_ID]))
      if (stopped()) return stopResult(done)
      let after = await s.capture.grab('verify')
      let changed = hashOf(after) !== hashOf(fresh)
      let how = ''
      // Typed text that did not show up: the keystrokes may have gone elsewhere. Retry ONCE by pasting (clipboard restored), and say so.
      if (!changed && step.tool === 'type' && actuator.pasteText && !stopped()) {
        const pr = await actuator.pasteText(step.text ?? '')
        how = pr.ok ? ' (typing did not show, so I pasted the text once)' : ' (typing did not show and pasting failed)'
        await audit({ decision: 'allowed', ok: pr.ok, code: pr.ok ? 'step' : 'failed', label: 'type: paste fallback', step: done })
        if (pr.ok) {
          await sleep(settleMs)
          after = await s.capture.grab('verify')
          changed = hashOf(after) !== hashOf(fresh)
        }
      }
      // Slow screens: wait a moment and look again before calling it no progress.
      if (!changed && !stopped()) {
        await sleep(settleMs * 2)
        const later = await s.capture.grab('verify')
        if (hashOf(later) !== hashOf(fresh)) {
          after = later
          changed = true
        }
      }
      unchanged = changed ? 0 : unchanged + 1
      lastNote = changed ? 'the screen changed after your last step' : 'the screen did not change after your last step'
      history.push(`${what} -> ${changed ? 'the screen changed' : 'no visible change'}${how}`)
      if (spot) safely(ctx, 'overlay', () => s.overlay.show([{ id: TICK_ID, kind: 'tick', tone: changed ? 'success' : 'warn', box: boxAroundPoint(spot, 30), ok: changed, ttlMs: 1500 }]))
      // No visible effect: the first miss gets ONE re-plan with feedback (the next click is re-grounded through Accessibility
      // again); a second miss in a row ends the task.
      if (unchanged >= 2) {
        await audit({ decision: 'allowed', ok: false, code: 'gave_up', label: 'no effect', step: done })
        return result('gave_up', true, false, 'Nothing on the screen changed after two steps in a row, so I stopped. Show the learner instead.', { steps: done })
      }
      if (unchanged === 1) feedback = `Your last step ("${oneLine(what, 80)}") had no visible effect; ${lastNote.replace(' after your last step', '')} (front app: ${frontNow ?? 'unknown'}); choose a DIFFERENT next step or finish.`
      carry = after
    }
    return result('gave_up', true, false, 'I stopped without finishing. Show the learner the rest.', { steps: done })

    async function perform(step: ProposedStep): Promise<ActResult> {
      switch (step.tool) {
        case 'click':
          return actuator.clickAt(step.point as NormPoint)
        case 'double_click':
          return actuator.clickAt(step.point as NormPoint, { double: true })
        case 'type':
          return actuator.typeText(step.text ?? '')
        case 'keys':
          return actuator.pressKeys(step.keys ?? '')
        case 'scroll':
          return actuator.scroll(step.point as NormPoint, step.dy ?? 0)
        case 'wait':
          return { ok: true }
      }
    }

    // The model says it is finished: success only if the Verifier agrees on a fresh screenshot.
    async function finish(goalText: string, said: string, steps: number): Promise<AgencyResult> {
      clearScreen()
      const note = said ? ` The helper said: "${oneLine(said, 160)}".` : ''
      if (steps === 0) {
        await audit({ decision: 'allowed', ok: false, code: 'gave_up', label: 'nothing to do', step: 0 })
        return result('gave_up', true, false, `I did not do anything: the helper could not find a safe step.${note} Show the learner how instead.`, { steps: 0 })
      }
      let verified = false
      let dryRun = false
      if (actuator.status().dryRun) {
        dryRun = true
      } else {
        try {
          const shot = await s.capture.grab('verify')
          const verdict = await s.verifier.verify({ expected: `The task "${goalText}" has been completed: the screen shows the result of it.`, shot })
          verified = verdict.completed && !verdict.uncertain
        } catch (err) {
          ctx.log('agency', 'final verify failed:', err instanceof Error ? err.message : err)
        }
      }
      if (dryRun) {
        await audit({ decision: 'allowed', ok: true, code: 'done', label: 'task', step: steps, dryRun: true })
        return result('done', true, true, `Dry run: ${steps} step${steps === 1 ? '' : 's'} were logged, not performed.`, { steps, dryRun: true })
      }
      if (!verified) {
        await audit({ decision: 'allowed', ok: false, code: 'gave_up', label: 'unverified', step: steps })
        return result('gave_up', true, false, `I did ${steps} step${steps === 1 ? '' : 's'} but I cannot be sure it worked.${note} Ask the learner to look at the screen with you; do not say it is done.`, { steps, verified: false })
      }
      await audit({ decision: 'allowed', ok: true, code: 'done', label: 'task', step: steps })
      const key = ctx.state.get().skill?.id ?? `task:${oneLine(goalText, 50).toLowerCase()}`
      try {
        await doneForMe(key)
      } catch (err) {
        ctx.log('agency', 'doneForMe count failed:', err instanceof Error ? err.message : err)
      }
      return result('done', true, true, `Done in ${steps} step${steps === 1 ? '' : 's'}, and the screen confirms it. Say in one short sentence what you did, and offer to show the learner how to do it themselves next time.`, { steps, verified: true })
    }
  }

  return {
    run,
    stop(): void {
      sit.epoch++
      sit.autonomyOff() // Stop ends autonomous for the rest of the session
      clearScreen()
    },
    isRunning: () => active !== null,
  }
}

