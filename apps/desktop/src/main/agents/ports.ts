// Agents are READ-ONLY by construction: each agent kind is handed only the narrow ports below.
// There is deliberately no port for sending, buying, typing, clicking, submitting forms, or speaking.
import type { Annotation, AgentChip, AgentKind, AgentPayload, AgentResult, GroundResult, LearnerSnapshot, ScamReport, Shot } from '../../shared/protocol'
import type { Settings } from '../../shared/settings'
import type { Capture, Grounder, LearnerStore, LiveBridge, OverlayController } from '../../shared/contracts'

export interface GroundedAnswer {
  text: string
  // Hostnames of the pages the answer was grounded on; empty means grounding found nothing.
  sources: string[]
}

// The only model call agents make themselves: a Search-grounded text answer. Reading messages off the screen is
// done by the ScamAnalyst, which sees the screenshot directly.
export interface AgentModelPort {
  searchAnswer(req: { system: string; prompt: string; signal: AbortSignal }): Promise<GroundedAnswer>
}

export interface ExportFs {
  mkdir(dir: string, opts: { recursive: true }): Promise<unknown>
  writeFile(file: string, data: string, opts: { encoding: 'utf8'; mode: number }): Promise<void>
}

export interface AgentDeps {
  state: { patch(patch: { agents: AgentChip[] }): void }
  bus: { emit(event: 'agent:update', payload: { chip: AgentChip }): void }
  capture: Pick<Capture, 'grab'>
  grounder: Grounder
  // `onProgress` is optional on the analyst: when it reports stages, the chip summary shows them live.
  scam: { analyze(req: { text?: string; shot?: Shot; url?: string }, opts?: { onProgress?: (message: string) => void }): Promise<ScamReport> }
  overlay: Pick<OverlayController, 'show' | 'clear'>
  live: LiveBridge
  learner: Pick<LearnerStore, 'snapshot'>
  settings: () => Settings
  model: AgentModelPort
  exportsDir: string
  fs?: ExportFs
  now?: () => number
}

export interface PortScope {
  agentId: string
  signal: AbortSignal
  now: () => number
  // Replaces the running chip's summary (status stays 'running'); ignored once the agent is settled or stopped.
  progress(message: string): void
  // Hands the result over now (chip -> done, [AGENT_RESULT] injected) while the agent keeps running, so slow
  // follow-up work such as drawing highlights never delays what the assistant says. Only the first call counts.
  announce(outcome: AgentOutcome): void
  // Overlay highlights are tracked per agent so cancel/timeout/clear_annotations can remove them.
  highlights: {
    show(annotations: Annotation[], ttlMs: number): void
  }
}

export interface ScamPorts {
  settings(): Settings
  grabScreen(): Promise<Shot>
  analyze(req: { text?: string; shot?: Shot; url?: string }): Promise<ScamReport>
  progress(message: string): void
  announce(outcome: AgentOutcome): void
  ground(target: string, shot: Shot, hint?: string): Promise<GroundResult>
  showHighlights(annotations: Annotation[], ttlMs: number): void
  now(): number
}

export interface LookupPorts {
  searchAnswer(req: { system: string; prompt: string }): Promise<GroundedAnswer>
}

export interface SummaryPorts {
  settings(): Settings
  learnerSnapshot(): LearnerSnapshot
  saveExport(fileName: string, markdown: string): Promise<string>
  now(): number
}

export interface AgentOutcome {
  summary: string
  result?: AgentResult
  // Text appended to the `[AGENT_RESULT …]` line the Live model hears. Built by us, never raw model/web text.
  tell: string
  title?: string
}

export interface AgentRunArgs<P> {
  agentId: string
  task: string
  payload: AgentPayload
  signal: AbortSignal
  ports: P
}

export interface AgentDefinition<P> {
  kind: AgentKind
  timeoutMs: number
  title(task: string, payload: AgentPayload): string
  createPorts(deps: AgentDeps, scope: PortScope): P
  run(args: AgentRunArgs<P>): Promise<AgentOutcome>
}

// Type-erased registry entry: the ports are built and consumed inside `execute`, so an agent
// can never be run with another kind's ports.
export interface RegisteredAgent {
  kind: AgentKind
  timeoutMs: number
  title(task: string, payload: AgentPayload): string
  execute(deps: AgentDeps, scope: PortScope, args: Omit<AgentRunArgs<unknown>, 'ports'>): Promise<AgentOutcome>
}

export function defineAgent<P>(def: AgentDefinition<P>): RegisteredAgent {
  return {
    kind: def.kind,
    timeoutMs: def.timeoutMs,
    title: def.title,
    execute: (deps, scope, args) => def.run({ ...args, ports: def.createPorts(deps, scope) }),
  }
}
