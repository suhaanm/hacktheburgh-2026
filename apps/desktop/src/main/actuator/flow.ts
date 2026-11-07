// The "do it for me" flow behind the do_it_for_me tool. Off by default (settings.doItForMeAllowed). Every click needs a
// fresh, real-click approval through ask_user_confirm (approval can never come from model text), is a single left click,
// and is audited. Anything money-, password-, sending-, deleting- or permission-shaped is refused: the assistant shows
// the target and leaves the click to the learner. Stop cancels the pending confirm and the click.
import type { Services } from '../../shared/contracts'
import type { Annotation, DoItForMeCode, DoItForMeResult, LessonStep, NormBox } from '../../shared/protocol'
import type { ConfirmBroker } from '../confirm'
import type { ServiceContext } from '../context'
import { appendAudit } from './audit'
import type { Actuator } from './index'
import { denylistMatch } from './policy'

export const APPROVE = 'Yes, do it'
export const DECLINE = 'No, I will'
const IDS = ['dfm-ring', 'dfm-ghost', 'dfm-bubble', 'dfm-tick']
const SHOW_MS = 12_000

export interface DoItForMeDeps {
  ctx: ServiceContext
  s: Pick<Services, 'capture' | 'grounder' | 'overlay' | 'verifier'>
  confirm: Pick<ConfirmBroker, 'ask'>
  actuator: Actuator
  // How long the UI gets to react before the Verifier looks (ms).
  settleMs?: number
}

const centre = (b: NormBox) => ({ x: (b.xmin + b.xmax) / 2, y: (b.ymin + b.ymax) / 2 })

export function createDoItForMe({ ctx, s, confirm, actuator, settleMs = 700 }: DoItForMeDeps): (args: { target: string }) => Promise<DoItForMeResult> {
  let currentStep: LessonStep | null = null
  ctx.bus.on('lesson:step', (e) => {
    currentStep = e.phase === 'done' || e.phase === 'aborted' ? null : (e.step ?? currentStep)
  })

  const result = (code: DoItForMeCode, allowed: boolean, done: boolean, reason: string, extra: Partial<DoItForMeResult> = {}): DoItForMeResult => ({ allowed, done, code, reason, ...extra })

  const audit = async (label: string, approved: boolean, r: DoItForMeResult): Promise<void> => {
    try {
      await appendAudit(ctx.userDataDir, { label, approved, ok: r.done, code: r.code, dryRun: r.dryRun })
    } catch (err) {
      ctx.log('actuator', 'audit write failed:', err instanceof Error ? err.message : err)
    }
  }

  const ring = (box: NormBox, label: string, ttlMs?: number): Annotation => ({ id: 'dfm-ring', kind: 'ring', tone: 'guide', box, label, ...(ttlMs ? { ttlMs } : {}) })

  return async ({ target }) => {
    if (!ctx.settings.get().doItForMeAllowed) {
      return result('setting_off', false, false, '"Let me do things for you" is switched off. Teach the learner to do it instead, and tell them they can switch it on in settings.')
    }

    const shot = await s.capture.grab('ground')
    const res = await s.grounder.ground({ target, shot, precise: true })
    s.overlay.clear(IDS)
    if (!res.found || !res.box) {
      return result('not_found', true, false, "I can't see that on the screen, so I will not click anything.")
    }
    const box = res.box
    const label = (res.label ?? target).slice(0, 80)

    // Refusals: show the target and leave the click to the learner.
    const state = ctx.state.get()
    const sensitive = denylistMatch(res.label, target)
    let refusal: { code: DoItForMeCode; reason: string } | null = null
    if (currentStep?.safetyCritical) refusal = { code: 'safety_step', reason: 'This lesson step involves something safety-critical, so the learner does it themselves. Show them, do not click.' }
    else if (state.skill?.id === 'spot_scam' || state.agents.some((a) => a.kind === 'scam_check' && a.status === 'running')) {
      refusal = { code: 'scam_check', reason: 'A scam check is in progress, so nothing is clicked for the learner. Show them where to look.' }
    } else if (sensitive) {
      refusal = { code: 'sensitive', reason: `"${sensitive}" could involve money, passwords, sending, deleting or permissions, so I never click that. I will show it and leave it to the learner.` }
    }
    if (refusal) {
      s.overlay.show([ring(box, label, SHOW_MS), { id: 'dfm-bubble', kind: 'bubble', tone: 'guide', at: { x: (box.xmin + box.xmax) / 2, y: box.ymin }, text: 'I will leave this one to you.', ttlMs: SHOW_MS }])
      const r = result(refusal.code, false, false, refusal.reason, { label })
      await audit(label, false, r)
      return r
    }

    const spot = centre(box)
    if (!actuator.canClick()) {
      s.overlay.show([ring(box, label, SHOW_MS), { id: 'dfm-ghost', kind: 'ghostCursor', tone: 'guide', path: [spot], ttlMs: SHOW_MS }])
      const r = result('accessibility', true, false, 'I cannot click for the learner yet: the computer has not given me the Accessibility permission. Explain that, and show them where to click instead.', { label })
      await audit(label, false, r)
      return r
    }

    s.overlay.show([ring(box, label), { id: 'dfm-ghost', kind: 'ghostCursor', tone: 'guide', path: [spot] }])

    let stopped = false
    const offEnded = ctx.bus.on('session:ended', () => {
      stopped = true
    })
    try {
      const choice = await confirm.ask(`I'll click "${label}" for you. OK?`, [APPROVE, DECLINE])
      // One approval buys exactly one click: it is consumed here and cannot be reused.
      const approved = choice === APPROVE && !stopped
      if (stopped) {
        s.overlay.clear(IDS)
        const r = result('stopped', true, false, 'Stop was pressed, so nothing was clicked.', { label })
        await audit(label, false, r)
        return r
      }
      if (!approved) {
        s.overlay.clear(IDS)
        const r = result('declined', true, false, 'The learner did not approve the click. Let them do it, and guide them.', { label })
        await audit(label, false, r)
        return r
      }
      if (!ctx.settings.get().doItForMeAllowed) {
        s.overlay.clear(IDS)
        const r = result('setting_off', false, false, '"Let me do things for you" was switched off while waiting, so nothing was clicked.', { label })
        await audit(label, true, r)
        return r
      }

      const click = await actuator.clickAt(spot)
      s.overlay.clear(['dfm-ghost'])
      if (!click.ok) {
        const code: DoItForMeCode = click.reason === 'accessibility' ? 'accessibility' : 'click_failed'
        const r = result(code, true, false, click.reason === 'accessibility' ? 'The Accessibility permission is missing, so nothing was clicked. Show the learner where to click.' : 'The click did not go through. Show the learner where to click.', { label })
        await audit(label, true, r)
        return r
      }

      let verified: boolean | undefined
      const dryRun = click.reason === 'dry-run'
      if (!dryRun) {
        try {
          await new Promise((r) => setTimeout(r, settleMs))
          const after = await s.capture.grab('verify')
          const verdict = await s.verifier.verify({ expected: `After clicking "${label}" the screen shows the result of that click: it has visibly changed.`, shot: after })
          verified = verdict.completed && !verdict.uncertain
          s.overlay.show([{ id: 'dfm-tick', kind: 'tick', tone: verified ? 'success' : 'warn', box, ok: verified }])
        } catch (err) {
          ctx.log('actuator', 'verify failed:', err instanceof Error ? err.message : err)
        }
      }
      const r = result('clicked', true, true, dryRun ? 'Dry run: the click was logged, not performed.' : 'I clicked it once.', { label, verified, dryRun })
      await audit(label, true, r)
      return r
    } finally {
      offEnded()
    }
  }
}
