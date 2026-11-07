import { afterEach, describe, expect, it, vi } from 'vitest'
import type { GoogleGenAI } from '@google/genai'
import { citedHosts, createAgentModelPort } from './gemini-port'
import { AgentUserError } from './errors'

afterEach(() => vi.unstubAllEnvs())

// Shape captured from a real gemini-3.8-flash + google_search response.
const REAL_STEPS = [
  { type: 'google_search_call' },
  { type: 'google_search_result' },
  { type: 'thought' },
  {
    type: 'model_output',
    content: [
      {
        type: 'text',
        annotations: [
          { type: 'url_citation', url: 'https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZ', title: 'support.apple.com', start_index: 0, end_index: 5 },
          { type: 'url_citation', url: 'https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZ2', title: 'support.apple.com', start_index: 6, end_index: 9 },
          { type: 'url_citation', url: 'https://www.abilitynet.org.uk/x', title: 'not a host', start_index: 10, end_index: 12 },
          { type: 'url_citation', url: 'https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZ3', title: 'no host here' },
        ],
      },
    ],
  },
]

function fakeClient(output: string, steps: unknown[] = []) {
  const calls: { params: Record<string, unknown>; options: unknown }[] = []
  const client = {
    interactions: {
      create: async (params: Record<string, unknown>, options: unknown) => {
        calls.push({ params, options })
        return { output_text: output, steps }
      },
    },
  } as unknown as GoogleGenAI
  return { client, calls }
}

describe('citedHosts', () => {
  it('uses the citation title as the host and ignores grounding redirects', () => {
    expect(citedHosts({ steps: REAL_STEPS })).toEqual(['support.apple.com', 'www.abilitynet.org.uk'.replace('www.', '')])
  })

  it('copes with missing or odd shapes', () => {
    expect(citedHosts({})).toEqual([])
    expect(citedHosts({ steps: [null, 3, { type: 'model_output' }, { type: 'model_output', content: [null] }] })).toEqual([])
  })
})

describe('agent model port', () => {
  it('search answers use google_search only, store:false, and no function declarations', async () => {
    const { client, calls } = fakeClient('1. Open Settings.', REAL_STEPS)
    const port = createAgentModelPort(client)
    const signal = new AbortController().signal
    const answer = await port.searchAnswer({ system: 'sys', prompt: 'q', signal })
    expect(answer.sources[0]).toBe('support.apple.com')
    const { params, options } = calls[0]!
    expect(params.tools).toEqual([{ type: 'google_search' }])
    expect(params.store).toBe(false)
    expect(JSON.stringify(params)).not.toMatch(/function_declarations|"type":"function"/)
    expect(options).toEqual({ signal })
  })

  it('fails with a plain message, not a stack, when no API key is configured', async () => {
    vi.stubEnv('GEMINI_API_KEY', '')
    const port = createAgentModelPort()
    await expect(port.searchAnswer({ system: 's', prompt: 'p', signal: new AbortController().signal })).rejects.toBeInstanceOf(AgentUserError)
  })
})
