// Mints short-lived ephemeral tokens so the real GEMINI_API_KEY never reaches a renderer.
// LEGACY REMOTE (D38): the wake-word spotter streams the microphone from a renderer to Gemini with this token, so the token is the only
// place main can stop it. `mintWakeToken` is DEFAULT OFF behind UNDERSTUDY_LEGACY_REMOTE=1 and, with the flag on, asks the gate (flag,
// privacy gates, a metadata ledger row of kind audio written first) before it contacts Gemini; a refusal throws and no token exists.
import { GoogleGenAI, Modality } from '@google/genai'
import { authorizeLegacy, LegacyRemoteBlocked, type LegacyRemoteGate } from './legacy-remote'
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

// REMOVED PATH: this minted a token for a Live socket opened FROM A RENDERER (the earlier Alongside session). Voice now lives in the main
// process (src/main/live), which mints its own model-locked token and holds the socket behind one choke point with the gates and the
// ledger. A renderer must not be able to open a Gemini socket, so the IPC that reaches this function (live:token) is refused.
export async function mintLiveToken(): Promise<LiveToken> {
  throw new Error('Voice no longer starts from the dock. Hold the talk key to speak (src/main/live).')
}

// Wake spotter: constrained to the transcribe model, text output + input transcription only.
export async function mintWakeToken(remote?: LegacyRemoteGate): Promise<LiveToken> {
  const model = MODELS.transcribe
  if (isMock()) return mockToken(model) // a stand-in token that opens nothing
  try {
    await authorizeLegacy({ kind: 'audio', purpose: 'legacy.wake_token', provider: 'gemini', model, bytes: 0, count: 1 }, { gate: remote })
  } catch (e) {
    if (e instanceof LegacyRemoteBlocked) throw new Error(e.userMessage)
    throw e
  }
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
