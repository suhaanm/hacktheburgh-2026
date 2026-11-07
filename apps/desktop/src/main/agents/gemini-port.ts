// The only model call agents make themselves. It goes out with store:false (spoken questions are not retained)
// and passes no function declarations, so a model can never call a tool.
import { GoogleGenAI } from '@google/genai'
import { MODELS } from '../../shared/models'
import { AgentUserError } from './errors'
import type { AgentModelPort, GroundedAnswer } from './ports'
import { hostOf } from './text-safety'

const NO_KEY_MESSAGE = 'I cannot reach my checking service right now. Please ask whoever set me up to look at my settings.'

interface Citation {
  title?: unknown
  url?: unknown
  type?: unknown
}

// Grounding URLs are redirects through vertexaisearch; the citation title is the real site's hostname.
export function citedHosts(interaction: { steps?: unknown }): string[] {
  const hosts: string[] = []
  const steps = Array.isArray(interaction.steps) ? (interaction.steps as unknown[]) : []
  for (const step of steps) {
    if (typeof step !== 'object' || step === null || (step as { type?: unknown }).type !== 'model_output') continue
    const content = (step as { content?: unknown }).content
    for (const block of Array.isArray(content) ? (content as unknown[]) : []) {
      const annotations = (block as { annotations?: unknown } | null)?.annotations
      for (const annotation of Array.isArray(annotations) ? (annotations as Citation[]) : []) {
        if (annotation.type !== 'url_citation') continue
        const fromTitle = typeof annotation.title === 'string' ? hostOf(annotation.title) : undefined
        const fromUrl = typeof annotation.url === 'string' ? hostOf(annotation.url) : undefined
        const host = fromTitle ?? (fromUrl && !fromUrl.endsWith('vertexaisearch.cloud.google.com') ? fromUrl : undefined)
        if (host && !hosts.includes(host)) hosts.push(host)
      }
    }
  }
  return hosts
}

export function createAgentModelPort(clientOverride?: GoogleGenAI): AgentModelPort {
  let client = clientOverride
  const getClient = (): GoogleGenAI => {
    if (client) return client
    const apiKey = process.env.GEMINI_API_KEY
    if (!apiKey) throw new AgentUserError(NO_KEY_MESSAGE)
    client = new GoogleGenAI({ apiKey })
    return client
  }

  return {
    async searchAnswer({ system, prompt, signal }): Promise<GroundedAnswer> {
      const interaction = await getClient().interactions.create(
        {
          model: MODELS.flash,
          system_instruction: system,
          input: prompt,
          tools: [{ type: 'google_search' }],
          store: false,
          generation_config: { thinking_level: 'low' },
        },
        { signal },
      )
      return { text: interaction.output_text ?? '', sources: citedHosts(interaction) }
    },
  }
}
