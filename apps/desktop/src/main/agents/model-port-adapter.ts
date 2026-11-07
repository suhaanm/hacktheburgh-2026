// The only model call agents make themselves: a web-search-grounded text answer, through the model port.
// The request carries no tools except hosted web search, so a model can never call a function; the provider adds store:false.
import { createModelPortFromEnv, ModelPortError, plainByCode, type ModelPort } from '../model-port'
import { AgentUserError } from './errors'
import type { AgentModelPort, GroundedAnswer } from './ports'
import { hostOf } from './text-safety'

// Hostnames of the cited pages, in first-seen order (the port already returns plain URLs).
export function citedHosts(citations: readonly string[]): string[] {
  const hosts: string[] = []
  for (const url of citations) {
    const host = hostOf(url)
    if (host && !hosts.includes(host)) hosts.push(host)
  }
  return hosts
}

export function createAgentModelPort(portOverride?: ModelPort): AgentModelPort {
  let port = portOverride
  const getPort = (): ModelPort => (port ??= createModelPortFromEnv())

  return {
    async searchAnswer({ system, prompt, signal }): Promise<GroundedAnswer> {
      if (signal.aborted) throw new AgentUserError('That was stopped.')
      try {
        const call = await getPort().complete({
          name: 'agents.search',
          tier: 'fast',
          system,
          text: prompt,
          effort: 'low',
          webSearch: true,
          timeoutMs: 20_000,
          retries: 0,
        })
        if (signal.aborted) throw new AgentUserError('That was stopped.')
        return { text: call.text, sources: citedHosts(call.citations ?? []) }
      } catch (e) {
        if (e instanceof AgentUserError) throw e
        // A person never sees a code: setup problems get the plain setup sentence, everything else a generic one.
        const code = e instanceof ModelPortError ? e.code : 'api'
        throw new AgentUserError(['auth', 'config'].includes(code) ? 'I cannot reach my checking service right now. Please ask whoever set me up to look at my settings.' : plainByCode(code))
      }
    },
  }
}
