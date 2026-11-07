// Mints short-lived ephemeral tokens so the real GEMINI_API_KEY never reaches a renderer.
import { GoogleGenAI, Modality } from '@google/genai'
import type { LiveToken } from '../shared/protocol'
import { MODELS } from '../shared/models'

function isMock(): boolean {
  return process.env.ALONGSIDE_MOCK === '1' || process.env.ALONGSIDE_MOCK_LIVE_AUTH === '1' || !process.env.GEMINI_API_KEY
}

function client(): GoogleGenAI {
  return new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY, httpOptions: { apiVersion: 'v1beta' } })
}

function mockToken(model: string): LiveToken {
  return { token: 'mock', model, expiresAt: Date.now() + 30 * 60_000 }
}

// Voice sessions: one new connection within 1 minute, usable for 30 minutes, resumption does not count as a use.
export async function mintLiveToken(): Promise<LiveToken> {
  const model = MODELS.live
  if (isMock()) return mockToken(model)
  const now = Date.now()
  const expireTime = new Date(now + 30 * 60_000).toISOString()
  const token = await client().authTokens.create({
    config: {
      uses: 1,
      expireTime,
      newSessionExpireTime: new Date(now + 60_000).toISOString(),
      httpOptions: { apiVersion: 'v1beta' },
    },
  })
  if (!token.name) throw new Error('Token service returned no token')
  return { token: token.name, model, expiresAt: now + 30 * 60_000 }
}

// Wake spotter: constrained to the transcribe model, text output + input transcription only.
export async function mintWakeToken(): Promise<LiveToken> {
  const model = MODELS.transcribe
  if (isMock()) return mockToken(model)
  const now = Date.now()
  const expireTime = new Date(now + 10 * 60_000).toISOString()
  const token = await client().authTokens.create({
    config: {
      uses: 1,
      expireTime,
      newSessionExpireTime: new Date(now + 60_000).toISOString(),
      liveConnectConstraints: {
        model,
        config: { responseModalities: [Modality.TEXT], inputAudioTranscription: {} },
      },
      httpOptions: { apiVersion: 'v1beta' },
    },
  })
  if (!token.name) throw new Error('Token service returned no token')
  return { token: token.name, model, expiresAt: now + 10 * 60_000 }
}
