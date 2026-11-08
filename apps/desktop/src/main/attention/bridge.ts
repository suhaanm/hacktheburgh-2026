// The producer bridge (REQ-8): turns what the shell can already read (the pending approvals, the agent runs, the briefing, the proposals,
// service health) into attention events, so the layer works without any other track changing a line. It polls through injected sources that
// return ids and enums only, diffs them against what it last saw, and reports `raise` when something appears and `resolve` when it is gone
// (an approval decided elsewhere, a run that moved on). The sources are the shell's: it already holds the engine and agent clients.
//
// Mapping (the approval queue kinds are services/agent queue.py KINDS):
//   queue kind injection_pause            -> injection_pause           (safety)
//   queue kind irreversible_step          -> irreversible_decision     (safety: an unattended run needs a decision about something that cannot be undone)
//   any other pending item, a job waits   -> approval_blocking         (time-sensitive)
//   any other pending item, nothing waits -> approval_waiting          (can wait; counts in the tray)
//   a run needing the worker              -> run_blocked_target | run_blocked_error
//   a run that ended                      -> run_finished              (can wait)
import type { AttentionEvent } from './types'
import { toSubject } from './types'

export interface QueueItemView {
  id: string
  kind: 'irreversible_step' | 'outward_step' | 'batch_result' | 'injection_pause' | 'shadow_mismatch' | 'browser_step'
  risk: 'irreversible' | 'outward' | 'normal'
  /** A running job is waiting for this decision. */
  blocksRun: boolean
  runId?: string | null
}
export interface RunView {
  id: string
  mode: 'overnight' | 'background' | 'foreground'
  state: 'running' | 'done' | 'failed' | 'paused' | 'yielded' | 'stopped'
  /** The run is paused for the worker: it could not find its target, or it reached an error page. */
  needsHuman?: 'target' | 'error' | null
}
export interface BriefingView {
  generation: string
  cards: number
}
export interface ProducerSources {
  approvals?: () => Promise<QueueItemView[] | null>
  runs?: () => Promise<RunView[] | null>
  briefing?: () => Promise<BriefingView | null>
  proposals?: () => Promise<Array<{ id: string }> | null>
  services?: () => Promise<Array<{ service: 'engine' | 'agent' | 'model' | 'calendar'; ok: boolean }> | null>
  /** The morning report of the agent runtime: an id and how many runs it lists. */
  morning?: () => Promise<{ id: string; runs: number } | null>
}

export interface ProducerBridge {
  /** Poll every source once and report what changed. Never throws. */
  pollOnce(): Promise<number>
}

type Report = (ev: AttentionEvent) => Promise<void>

export function createProducerBridge(sources: ProducerSources, report: Report): ProducerBridge {
  // What each source showed last time, by event key ("type|subject"), so a raise happens once and a resolve when it disappears.
  const seen = new Map<string, AttentionEvent>()

  async function reconcile(scope: string, now: AttentionEvent[] | null): Promise<number> {
    if (now === null) return 0 // the source did not answer: change nothing (never resolve on a failed read)
    let n = 0
    const keys = new Set(now.map((e) => `${e.type}|${e.subject}`))
    for (const e of now) {
      const k = `${e.type}|${e.subject}`
      if (!seen.has(k)) {
        seen.set(k, e)
        await report(e)
        n += 1
      }
    }
    for (const [k, e] of [...seen]) {
      if (scopeOf(e) === scope && !keys.has(k)) {
        seen.delete(k)
        await report({ type: e.type, subject: e.subject, op: 'resolve' })
        n += 1
      }
    }
    return n
  }

  const scopeOf = (e: AttentionEvent): string => {
    if (e.type === 'injection_pause' || e.type === 'irreversible_decision' || e.type === 'approval_blocking' || e.type === 'approval_waiting') return 'approvals'
    if (e.type === 'run_blocked_target' || e.type === 'run_blocked_error' || e.type === 'run_finished') return 'runs'
    if (e.type === 'briefing_ready') return 'briefing'
    if (e.type === 'routine_proposal') return 'proposals'
    if (e.type === 'service_degraded') return 'services'
    return 'morning'
  }

  const safe = async <T>(fn: (() => Promise<T | null>) | undefined): Promise<T | null> => {
    if (!fn) return null
    try {
      return await fn()
    } catch {
      return null
    }
  }

  return {
    async pollOnce() {
      let n = 0
      if (sources.approvals) {
        const items = await safe(sources.approvals)
        n += await reconcile('approvals', items === null ? null : items.map(approvalEvent))
      }
      if (sources.runs) {
        const runs = await safe(sources.runs)
        n += await reconcile('runs', runs === null ? null : runs.flatMap(runEvents))
      }
      if (sources.briefing) {
        const b = await safe(sources.briefing)
        n += await reconcile('briefing', b === null ? [] : b.cards > 0 ? [{ type: 'briefing_ready', subject: toSubject(`gen_${b.generation}`), count: Math.min(999, b.cards) }] : [])
      }
      if (sources.proposals) {
        const p = await safe(sources.proposals)
        n += await reconcile('proposals', p === null ? null : p.map((x) => ({ type: 'routine_proposal' as const, subject: toSubject(x.id) })))
      }
      if (sources.services) {
        const s = await safe(sources.services)
        n += await reconcile('services', s === null ? null : s.filter((x) => !x.ok).map((x) => ({ type: 'service_degraded' as const, subject: `svc_${x.service}`, service: x.service })))
      }
      if (sources.morning) {
        const m = await safe(sources.morning)
        n += await reconcile('morning', m === null ? [] : m.runs > 0 ? [{ type: 'morning_report', subject: toSubject(`report_${m.id}`), count: Math.min(999, m.runs) }] : [])
      }
      return n
    },
  }
}

export function approvalEvent(i: QueueItemView): AttentionEvent {
  const subject = toSubject(i.runId ? `${i.runId}` : i.id)
  if (i.kind === 'injection_pause') return { type: 'injection_pause', subject, risk_class: i.risk }
  if (i.kind === 'irreversible_step') return { type: 'irreversible_decision', subject, risk_class: 'irreversible', run_mode: 'overnight' }
  return { type: i.blocksRun ? 'approval_blocking' : 'approval_waiting', subject: toSubject(i.id), risk_class: i.risk, blocks_run: i.blocksRun }
}

export function runEvents(r: RunView): AttentionEvent[] {
  const subject = toSubject(r.id)
  if (r.state === 'running') return []
  if (r.state === 'paused' && r.needsHuman) {
    return [{ type: r.needsHuman === 'error' ? 'run_blocked_error' : 'run_blocked_target', subject, run_mode: r.mode }]
  }
  if (r.state === 'paused') return []
  return [{ type: 'run_finished', subject, run_mode: r.mode, outcome: r.state === 'done' ? 'done' : r.state === 'failed' ? 'failed' : r.state === 'yielded' ? 'yielded' : 'stopped' }]
}
