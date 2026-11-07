import { describe, expect, it } from 'vitest'
import { createMockProvider, createModelPort, ModelPortError, type CompletionRequest } from '../model-port'
import { AgentUserError } from './errors'
import { citedHosts, createAgentModelPort } from './model-port-adapter'

function portWith(respond: (req: CompletionRequest) => { text: string; citations?: string[] } | Error) {
  const calls: CompletionRequest[] = []
  const base = createMockProvider()
  const port = createModelPort({
    ...base,
    async complete(req) {
      calls.push(req)
      const r = respond(req)
      if (r instanceof Error) throw r
      return { text: r.text, citations: r.citations, model: 'm', ms: 1 }
    },
  })
  return { port, calls }
}

describe('citedHosts', () => {
  it('returns hostnames in first-seen order without duplicates and ignores junk', () => {
    expect(citedHosts(['https://support.apple.com/a', 'https://support.apple.com/b', 'https://www.abilitynet.org.uk/x', 'not a url', ''])).toEqual(['support.apple.com', 'abilitynet.org.uk'])
    expect(citedHosts([])).toEqual([])
  })
})

describe('agent model port (through the model port)', () => {
  it('asks for a web-search answer on the fast tier with no schema or function tools, and reports cited hosts', async () => {
    const { port, calls } = portWith(() => ({ text: '1. Open Settings.', citations: ['https://support.apple.com/x'] }))
    const answer = await createAgentModelPort(port).searchAnswer({ system: 'sys', prompt: 'q', signal: new AbortController().signal })
    expect(answer).toEqual({ text: '1. Open Settings.', sources: ['support.apple.com'] })
    expect(calls).toHaveLength(1)
    expect(calls[0]).toMatchObject({ tier: 'fast', webSearch: true, system: 'sys', text: 'q' })
    expect(calls[0].schema).toBeUndefined()
  })

  it('turns a setup problem into one plain sentence and never exposes a code', async () => {
    const { port } = portWith(() => new ModelPortError('config', 'OPENAI_MODEL_FAST is not set'))
    const err = await createAgentModelPort(port).searchAnswer({ system: 's', prompt: 'p', signal: new AbortController().signal }).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(AgentUserError)
    expect((err as AgentUserError).userMessage).toMatch(/cannot reach my checking service/)
    expect((err as AgentUserError).userMessage).not.toMatch(/OPENAI/)
  })

  it('does not call the model when already stopped', async () => {
    const { port, calls } = portWith(() => ({ text: 'x' }))
    const stop = new AbortController()
    stop.abort()
    await expect(createAgentModelPort(port).searchAnswer({ system: 's', prompt: 'p', signal: stop.signal })).rejects.toBeInstanceOf(AgentUserError)
    expect(calls).toHaveLength(0)
  })
})
