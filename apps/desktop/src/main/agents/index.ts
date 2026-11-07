import { createAgentRuntime } from './runtime'
import type { AgentRuntimeApi } from './runtime'
import type { AgentDeps } from './ports'
import { scamCheckAgent } from './scam-check'
import { lookupAgent } from './lookup'
import { lessonSummaryAgent } from './lesson-summary'

export type { AgentDeps, AgentModelPort, GroundedAnswer } from './ports'
export type { AgentRuntimeApi } from './runtime'
export { AgentUserError, toPlainMessage } from './errors'

const AGENTS = [scamCheckAgent, lookupAgent, lessonSummaryAgent] as const

/** The three agent kinds are the whole allow-list: there is no kind that can send, buy, click or submit. */
export function createAgents(deps: AgentDeps): AgentRuntimeApi {
  return createAgentRuntime(deps, AGENTS)
}
