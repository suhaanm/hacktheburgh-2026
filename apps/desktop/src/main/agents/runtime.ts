import { randomBytes } from 'node:crypto'
import { AgentPayloadSchema } from '../../shared/protocol'
import type { AgentChip, AgentKind, AgentPayload, Annotation } from '../../shared/protocol'
import type { AgentRuntime } from '../../shared/contracts'
import { AgentCancelledError, AgentTimeoutError, AgentUserError, GENERIC_MESSAGE, logAgentError, toPlainMessage } from './errors'
import type { AgentDeps, AgentOutcome, PortScope, RegisteredAgent } from './ports'
import { cleanText, inlineSafe } from './text-safety'

export const MAX_CONCURRENT_AGENTS = 3
export const DEFAULT_TIMEOUT_MS = 30_000
export const MAX_TASK_CHARS = 1000
export const MAX_MESSAGE_CHARS = 6000
const KEEP_FINISHED_CHIPS = 5
const MAX_INJECT_CHARS = 900

interface RunningAgent {
  chip: AgentChip
  controller: AbortController
  timer: ReturnType<typeof setTimeout>
  settled: boolean
}

// Highlights are drawn one at a time as they are located, each with its own expiry.
interface HighlightGroup {
  ids: Set<string>
  timers: Set<ReturnType<typeof setTimeout>>
}

export interface AgentRuntimeApi extends AgentRuntime {
  /** Removes every scam highlight now (wired to `clear_annotations`). */
  clearHighlights(): void
  /** Cancels everything that is running and removes highlights (the big Stop control). */
  cancelAll(): void
  dispose(): void
}

function sanitizePayload(raw: AgentPayload | undefined): AgentPayload {
  const parsed = AgentPayloadSchema.safeParse(raw ?? {})
  if (!parsed.success) throw new AgentUserError('I could not understand what to check. Please ask me again.', 'bad_request')
  const clean: AgentPayload = {}
  if (parsed.data.text) {
    const text = cleanText(parsed.data.text, MAX_MESSAGE_CHARS)
    if (text) clean.text = text
  }
  if (parsed.data.url) {
    const url = parsed.data.url.trim().slice(0, 500)
    // Only ever handed to the analyst as data. Agents never open links themselves.
    if (/^https?:\/\/\S+$/i.test(url)) clean.url = url
  }
  if (parsed.data.useScreen) clean.useScreen = true
  return clean
}

export function formatAgentResultLine(kind: AgentKind, id: string, status: AgentChip['status'], body: string): string {
  return `[AGENT_RESULT kind=${kind} id=${id} status=${status}] ${inlineSafe(body, MAX_INJECT_CHARS)}`
}

export function createAgentRuntime(deps: AgentDeps, agents: readonly RegisteredAgent[]): AgentRuntimeApi {
  const registry = new Map<AgentKind, RegisteredAgent>(agents.map((a) => [a.kind, a]))
  const now = deps.now ?? Date.now
  const running = new Map<string, RunningAgent>()
  const highlights = new Map<string, HighlightGroup>()
  let chips: AgentChip[] = []
  let seq = 0

  function visibleChips(): AgentChip[] {
    const finished = chips.filter((c) => c.status !== 'running')
    const dropped = new Set(finished.slice(0, Math.max(0, finished.length - KEEP_FINISHED_CHIPS)).map((c) => c.id))
    chips = chips.filter((c) => !dropped.has(c.id))
    return chips
  }

  function publish(chip: AgentChip): void {
    try {
      deps.state.patch({ agents: visibleChips().map((c) => ({ ...c })) })
      deps.bus.emit('agent:update', { chip: { ...chip } })
    } catch (err) {
      logAgentError('publish', err)
    }
  }

  function clearOverlayIds(ids: string[]): void {
    try {
      deps.overlay.clear(ids)
    } catch (err) {
      logAgentError('overlay.clear', err)
    }
  }

  function clearAgentHighlights(agentId: string): void {
    const group = highlights.get(agentId)
    if (!group) return
    highlights.delete(agentId)
    for (const timer of group.timers) clearTimeout(timer)
    clearOverlayIds([...group.ids])
  }

  function showHighlights(agentId: string, signal: AbortSignal, annotations: Annotation[], ttlMs: number): void {
    if (signal.aborted || annotations.length === 0) return
    try {
      deps.overlay.show(annotations)
    } catch (err) {
      logAgentError('overlay.show', err)
      return
    }
    const group = highlights.get(agentId) ?? { ids: new Set<string>(), timers: new Set<ReturnType<typeof setTimeout>>() }
    highlights.set(agentId, group)
    const ids = annotations.map((a) => a.id)
    for (const id of ids) group.ids.add(id)
    const timer = setTimeout(() => {
      group.timers.delete(timer)
      for (const id of ids) group.ids.delete(id)
      clearOverlayIds(ids)
      if (group.ids.size === 0 && group.timers.size === 0) highlights.delete(agentId)
    }, ttlMs)
    timer.unref?.()
    group.timers.add(timer)
  }

  function inject(text: string): void {
    try {
      deps.live.inject(text, { interrupt: false })
    } catch (err) {
      logAgentError('live.inject', err)
    }
  }

  function settle(run: RunningAgent, status: AgentChip['status'], summary: string, outcome?: AgentOutcome, tell?: string): void {
    if (run.settled) return
    run.settled = true
    run.chip = {
      ...run.chip,
      status,
      summary,
      ...(outcome?.result ? { result: outcome.result } : {}),
      ...(outcome?.title ? { title: outcome.title } : {}),
    }
    chips = chips.map((c) => (c.id === run.chip.id ? run.chip : c))
    if (status !== 'done') clearAgentHighlights(run.chip.id)
    publish(run.chip)
    // A chip the user stopped is never announced; everything else is told to the Live model.
    if (status !== 'cancelled' && tell) inject(formatAgentResultLine(run.chip.kind, run.chip.id, status, tell))
  }

  function progress(run: RunningAgent, message: string): void {
    if (run.settled || run.controller.signal.aborted) return
    const summary = inlineSafe(message, 120)
    if (!summary || summary === run.chip.summary) return
    run.chip = { ...run.chip, summary }
    chips = chips.map((c) => (c.id === run.chip.id ? run.chip : c))
    publish(run.chip)
  }

  async function execute(agent: RegisteredAgent, run: RunningAgent, task: string, payload: AgentPayload): Promise<void> {
    const { signal } = run.controller
    const scope: PortScope = {
      agentId: run.chip.id,
      signal,
      now,
      progress: (message) => progress(run, message),
      // Lets an agent hand over its result the moment it exists and keep working (e.g. drawing highlights).
      announce: (outcome) => settle(run, 'done', outcome.summary, outcome, outcome.tell),
      highlights: { show: (annotations, ttlMs) => showHighlights(run.chip.id, signal, annotations, ttlMs) },
    }
    const aborted = new Promise<never>((_, reject) => {
      signal.addEventListener('abort', () => reject(signal.reason), { once: true })
    })
    aborted.catch(() => undefined)
    try {
      const outcome = await Promise.race([Promise.resolve().then(() => agent.execute(deps, scope, { agentId: run.chip.id, task, payload, signal })), aborted])
      settle(run, 'done', outcome.summary, outcome, outcome.tell)
    } catch (err) {
      if (run.settled) {
        // Already announced: a stop or timeout only ends the follow-up work, and takes its highlights away.
        if (signal.aborted) clearAgentHighlights(run.chip.id)
        else logAgentError(agent.kind, err)
        return
      }
      if (signal.aborted && signal.reason instanceof AgentCancelledError) {
        settle(run, 'cancelled', 'Stopped.')
        return
      }
      const timedOut = signal.aborted && signal.reason instanceof AgentTimeoutError
      if (!timedOut && !(err instanceof AgentUserError)) logAgentError(agent.kind, err)
      const message = timedOut ? toPlainMessage(new AgentTimeoutError()) : toPlainMessage(err)
      settle(run, 'error', message, undefined, `The ${agent.kind.replace('_', ' ')} could not be finished. ${message} Tell the user kindly in one short sentence and offer to try again.`)
    } finally {
      // The slot (and timeout) are held until the follow-up work ends, not just until the result is announced.
      clearTimeout(run.timer)
      running.delete(run.chip.id)
    }
  }

  function cancelAll(): void {
    for (const run of [...running.values()]) run.controller.abort(new AgentCancelledError())
    for (const agentId of [...highlights.keys()]) clearAgentHighlights(agentId)
  }

  return {
    async spawn(kind, task, payload) {
      const agent = registry.get(kind)
      if (!agent) throw new AgentUserError('I do not know how to do that one yet.', 'bad_request')
      const cleanTask = cleanText(task ?? '', MAX_TASK_CHARS)
      if (!cleanTask) throw new AgentUserError('I did not catch what to look at. Please ask me again.', 'bad_request')
      if (running.size >= MAX_CONCURRENT_AGENTS) {
        throw new AgentUserError('I am already working on three things. Let me finish one first, then ask me again.', 'busy')
      }
      const cleanPayload = sanitizePayload(payload)
      const id = `agent-${++seq}-${randomBytes(2).toString('hex')}`
      const controller = new AbortController()
      const chip: AgentChip = { id, kind, title: inlineSafe(agent.title(cleanTask, cleanPayload), 80), status: 'running', startedAt: now() }
      const run: RunningAgent = {
        chip,
        controller,
        settled: false,
        timer: setTimeout(() => controller.abort(new AgentTimeoutError()), agent.timeoutMs),
      }
      running.set(id, run)
      chips = [...chips, chip]
      publish(chip)
      void execute(agent, run, cleanTask, cleanPayload).catch((err) => {
        logAgentError(kind, err)
        settle(run, 'error', GENERIC_MESSAGE)
        running.delete(id)
      })
      return { agentId: id }
    },

    list: () => chips.map((c) => ({ ...c })),

    cancel(id) {
      const run = running.get(id)
      if (run && !run.controller.signal.aborted) run.controller.abort(new AgentCancelledError())
    },

    clearHighlights() {
      for (const agentId of [...highlights.keys()]) clearAgentHighlights(agentId)
    },

    cancelAll,

    dispose: cancelAll,
  }
}

