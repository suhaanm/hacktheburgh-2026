// Proposal toasts (HND-1, HND-7): when the engine proposes a routine (GET /routines, status "proposed"), the worker sees ONE calm
// toast at a natural break, never mid-task. The rules, all deterministic code:
//   - not while a lesson or session is running, an approval is open, the screen is locked or everything is stopped;
//   - only after a pause: idle for a while, or an episode just ended and the keyboard is quiet;
//   - while the engine says a task is in progress (GET /coach/state), only after its last step;
//   - at most `maxPerDay` toasts a day and `minGapMs` apart;
//   - "Not now" snoozes that routine for hours, "Never for this" and "Look at it" stop the toasts for it (the dashboard owns the
//     rest of the consent), and a toast nobody answers leaves after `visibleMs` and comes back later, at most twice.
// A decline is also sent to the engine (a decline is a label, HND-7). The only consents the desktop sends are not_now and never.
import fs from 'node:fs'
import path from 'node:path'
import type { HudProposal } from '../shared/hud'
import type { AttentionEvent } from './attention/types'
import type { RoutineProposal } from './engine/client'

export interface BreakSignals {
  idleSeconds(): number
  lessonActive(): boolean
  confirmPending(): boolean
  killed(): boolean
  locked(): boolean
  // The task the engine says is in progress, or null.
  task(): { step: number; stepsTotal: number } | null
  // When the last episode (lesson, session or engine task) ended, ms since epoch, or null.
  lastEpisodeEndAt(): number | null
  // When the coach brain last said something other than silence (GET /coach/next): a prompt in the last minute means mid-task.
  lastCoachDecisionAt?(): number | null
}

export interface BreakRules {
  idleBreakS: number // a pause this long is a break by itself
  afterEpisodeIdleS: number // a quieter pause is enough shortly after an episode
  afterEpisodeWindowMs: number
  midTaskIdleS: number // while the engine says a task is in progress, the pause must be this long
  coachQuietMs: number // after a coach prompt this long counts as mid-task
}

export const DEFAULT_RULES: BreakRules = { idleBreakS: 15, afterEpisodeIdleS: 3, afterEpisodeWindowMs: 90_000, midTaskIdleS: 90, coachQuietMs: 60_000 }

export function isNaturalBreak(s: BreakSignals, now: number, rules: BreakRules = DEFAULT_RULES): boolean {
  if (s.killed() || s.locked() || s.confirmPending() || s.lessonActive()) return false
  const idle = s.idleSeconds()
  const task = s.task()
  const decidedAt = s.lastCoachDecisionAt?.() ?? null
  const coachBusy = decidedAt !== null && now - decidedAt <= rules.coachQuietMs
  const unfinished = !!task && task.step < task.stepsTotal
  // A task in progress, or a coach prompt a moment ago: the worker is in the middle of something, so only a long pause is a break.
  if (unfinished || coachBusy) return idle >= rules.midTaskIdleS
  const ended = s.lastEpisodeEndAt()
  if (ended !== null && now - ended <= rules.afterEpisodeWindowMs && idle >= rules.afterEpisodeIdleS) return true
  return idle >= rules.idleBreakS
}

// ---------- what has been offered ----------
interface RoutineMemory {
  // 'snoozed' until `until`; 'never' and 'looked' for good; 'ignored' counts toasts nobody answered.
  state?: 'snoozed' | 'never' | 'looked'
  until?: number
  ignored?: number
  lastIgnoredAt?: number
}
export interface ProposalMemory {
  day: string
  shownToday: number
  lastShownAt: number | null
  routines: Record<string, RoutineMemory>
}

export const emptyMemory = (day: string): ProposalMemory => ({ day, shownToday: 0, lastShownAt: null, routines: {} })
export const dayOf = (t: number): string => {
  const d = new Date(t)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export interface ProposalStore {
  load(): ProposalMemory | null
  save(m: ProposalMemory): void
}

export function fileProposalStore(userDataDir: string | null): ProposalStore {
  const file = userDataDir ? path.join(userDataDir, 'proposals-state.json') : null
  return {
    load() {
      if (!file) return null
      try {
        const j = JSON.parse(fs.readFileSync(file, 'utf8')) as ProposalMemory
        return j && typeof j.day === 'string' && typeof j.routines === 'object' ? j : null
      } catch {
        return null
      }
    },
    save(m) {
      if (!file) return
      try {
        fs.mkdirSync(path.dirname(file), { recursive: true })
        fs.writeFileSync(file, JSON.stringify(m), { mode: 0o600 })
      } catch {
        /* losing this only means a toast may be offered again */
      }
    },
  }
}

// REQ-8: with the attention layer on, a proposal is an event the layer decides about (whether, where, when, how loudly), not a toast this
// scheduler draws. It reports `routine_proposal` for each routine the engine says is proposed and `resolve` when it no longer is.
export interface ProposalAttention {
  report(ev: AttentionEvent): Promise<void> | void
}

export interface SchedulerDeps {
  engine: { routines(): Promise<RoutineProposal[] | null>; decline(id: string, mode: 'not_now' | 'never'): Promise<boolean> }
  hud: { setProposal(p: HudProposal | null): void; state(): { proposal: HudProposal | null } }
  signals: BreakSignals
  store?: ProposalStore
  now?: () => number
  rules?: Partial<BreakRules>
  maxPerDay?: number
  minGapMs?: number
  snoozeMs?: number
  reofferAfterIgnoredMs?: number
  maxIgnores?: number
  visibleMs?: number
  pollMs?: number // how often GET /routines is asked
  checkMs?: number // how often the break rules are checked while a candidate waits
  // The attention layer. Absent: the HUD toast, exactly as before. `setAttention` binds it later (it starts after the scheduler exists).
  attention?: ProposalAttention | null
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
  log?: (scope: string, ...args: unknown[]) => void
}

export interface ProposalScheduler {
  // One round: refresh the list if due, show a toast if a candidate is waiting and it is a natural break. Resolves with what it did.
  tick(): Promise<'shown' | 'waiting' | 'none' | 'budget' | 'not_a_break' | 'showing' | 'reported'>
  // The worker's choice on the toast (the HUD calls this).
  choice(id: string, choice: 'not_now' | 'never' | 'look'): void
  // Late binding for the attention layer. null goes back to the HUD toast (what was reported is left for the layer to expire).
  setAttention(a: ProposalAttention | null): void
  // "Not now" or "Never for this" pressed on the attention notice (which does not say which routine it was for). Applied only when exactly one
  // routine is outstanding with the layer; with several it is ambiguous, so nothing is declined here (the layer's own feedback still lands)
  // and false is returned.
  noticeChoice(choice: 'not_now' | 'never'): boolean
  memory(): ProposalMemory
  dispose(): void
}

export function toHudProposal(p: RoutineProposal): HudProposal {
  return { id: p.id, title: p.title, what: p.what || p.title, howOften: p.howOften, hoursSaved: p.hoursSaved, horizonWeeks: p.horizonWeeks, touches: p.touches, never: p.never }
}

export function createProposalScheduler(deps: SchedulerDeps): ProposalScheduler {
  const now = deps.now ?? Date.now
  const rules: BreakRules = { ...DEFAULT_RULES, ...deps.rules }
  const maxPerDay = deps.maxPerDay ?? 3
  const minGapMs = deps.minGapMs ?? 20 * 60_000
  const snoozeMs = deps.snoozeMs ?? 4 * 3_600_000
  const reofferMs = deps.reofferAfterIgnoredMs ?? 2 * 3_600_000
  const maxIgnores = deps.maxIgnores ?? 2
  const visibleMs = deps.visibleMs ?? 45_000
  const pollMs = deps.pollMs ?? 60_000
  const checkMs = deps.checkMs ?? 5_000
  const setT = deps.setTimer ?? ((fn, ms) => setInterval(fn, ms))
  const clearT = deps.clearTimer ?? ((h) => clearInterval(h as ReturnType<typeof setInterval>))
  const log = deps.log ?? (() => undefined)

  let mem: ProposalMemory = deps.store?.load() ?? emptyMemory(dayOf(now()))
  let list: RoutineProposal[] = []
  let listAt = -Infinity
  let showing: { id: string; hideTimer: unknown } | null = null
  let busy = false
  let attention: ProposalAttention | null = deps.attention ?? null
  // The routines reported to the attention layer and not yet resolved.
  const raised = new Set<string>()

  const save = (): void => deps.store?.save(mem)
  const rollDay = (): void => {
    const d = dayOf(now())
    if (mem.day !== d) {
      mem = { ...mem, day: d, shownToday: 0 }
      save()
    }
  }
  const rm = (id: string): RoutineMemory => (mem.routines[id] ??= {})

  const eligible = (p: RoutineProposal): boolean => {
    if (p.status !== 'proposed') return false
    const r = mem.routines[p.id]
    if (!r) return true
    if (r.state === 'never' || r.state === 'looked') return false
    if (r.state === 'snoozed' && (r.until ?? 0) > now()) return false
    if ((r.ignored ?? 0) >= maxIgnores) return false
    if ((r.ignored ?? 0) > 0 && now() - (r.lastIgnoredAt ?? 0) < reofferMs) return false
    return true
  }

  const hide = (): void => {
    if (!showing) return
    clearT(showing.hideTimer)
    showing = null
    deps.hud.setProposal(null)
  }

  const onIgnored = (id: string): void => {
    log('proposals', 'a toast was not answered; it leaves and may return later')
    const r = rm(id)
    r.ignored = (r.ignored ?? 0) + 1
    r.lastIgnoredAt = now()
    if (r.ignored >= maxIgnores) {
      r.state = 'snoozed' // two ignores: a day's rest, then a clean slate
      r.until = now() + 24 * 3_600_000
      r.ignored = 0
    }
    hide()
    save()
  }

  const declinedHere = (id: string): boolean => {
    const r = mem.routines[id]
    return !!r && (r.state === 'never' || (r.state === 'snoozed' && (r.until ?? 0) > now()))
  }

  // Attention mode: no budget, break rules or toast here (the layer decides all of that); just say what is proposed and what no longer is.
  const reportToLayer = (layer: ProposalAttention): 'reported' | 'none' => {
    const wanted = new Set(list.filter((p) => p.status === 'proposed' && !declinedHere(p.id)).map((p) => p.id))
    let n = 0
    for (const id of wanted) {
      if (raised.has(id)) continue
      raised.add(id)
      n += 1
      void Promise.resolve(layer.report({ type: 'routine_proposal', subject: id })).catch(() => undefined)
    }
    for (const id of [...raised]) {
      if (wanted.has(id)) continue
      raised.delete(id)
      void Promise.resolve(layer.report({ type: 'routine_proposal', subject: id, op: 'resolve' })).catch(() => undefined)
    }
    return n > 0 ? 'reported' : 'none'
  }

  const tick: ProposalScheduler['tick'] = async () => {
    if (busy) return 'waiting'
    busy = true
    try {
      rollDay()
      if (showing) return 'showing'
      if (now() - listAt >= pollMs) {
        const fresh = await deps.engine.routines()
        listAt = now()
        if (fresh) list = fresh // a failed read keeps the last list, so nothing is resolved on it
      }
      if (attention) return reportToLayer(attention)
      const candidates = list.filter(eligible).sort((a, b) => (b.hoursSaved?.[0] ?? 0) - (a.hoursSaved?.[0] ?? 0))
      if (candidates.length === 0) return 'none'
      if (mem.shownToday >= maxPerDay || (mem.lastShownAt !== null && now() - mem.lastShownAt < minGapMs)) return 'budget'
      if (!isNaturalBreak(deps.signals, now(), rules)) return 'not_a_break'
      const pick = candidates[0]
      mem.shownToday += 1
      mem.lastShownAt = now()
      save()
      deps.hud.setProposal(toHudProposal(pick))
      // The HUD refuses while stopped: only count it as showing if it actually is.
      if (deps.hud.state().proposal?.id !== pick.id) return 'waiting'
      showing = { id: pick.id, hideTimer: setT(() => onIgnored(pick.id), visibleMs) }
      return 'shown'
    } finally {
      busy = false
    }
  }

  const handle = setT(() => void tick(), checkMs)

  const choose = (id: string, choice: 'not_now' | 'never' | 'look'): void => {
    if (showing?.id === id) {
      clearT(showing.hideTimer)
      showing = null
    }
    const r = rm(id)
    if (choice === 'not_now') {
      r.state = 'snoozed'
      r.until = now() + snoozeMs
      void deps.engine.decline(id, 'not_now')
    } else if (choice === 'never') {
      r.state = 'never'
      void deps.engine.decline(id, 'never')
    } else r.state = 'looked'
    save()
  }

  return {
    tick,
    choice: choose,
    setAttention(a) {
      attention = a
    },
    noticeChoice(choice) {
      if (raised.size !== 1) return false
      choose([...raised][0] as string, choice)
      return true
    },
    memory: () => mem,
    dispose() {
      clearT(handle)
      if (showing) clearT(showing.hideTimer)
    },
  }
}
