import { GoogleGenAI, Modality, type LiveServerMessage, type Session } from '@google/genai'
import { pcm16ToBase64 } from './preroll'
import type { WakeEngine, WakeEngineFactory, WakeEngineHandlers, WakeToken } from './types'

export const TRANSCRIBE_MODEL = 'gemini-3.5-transcribe-live'

export interface GeminiEngineOptions {
  getToken(): Promise<WakeToken>
  // Bias recognition toward the persona names (derived from wakePhrases). Up to ~100 terms work best.
  vocabulary?: readonly string[]
  // Language hints. Without them the recogniser auto-detects and mangles short names ("Hey Amelia" -> "miudo",
  // "Hey Marcus" -> "Hey Maracas") on some voices; English hints fixed every such case in the spike.
  languageCodes?: readonly string[]
  model?: string
  // Pass 'v1alpha' when authenticating with an ephemeral token (the default here); Node tests with a raw key use 'v1beta'.
  apiVersion?: string
}

const MOCK_TOKEN = 'mock'

// Streams PCM16 16 kHz to gemini-3.5-transcribe-live and forwards interim + final transcripts.
// Interim hypotheses arrive ~0.35 s after the end of a spoken name (see docs/WAKE_SPIKE.md); we match on those,
// because a short utterance's final transcript can take over a second or never arrive before more audio does.
export function createGeminiEngineFactory(options: GeminiEngineOptions): WakeEngineFactory {
  return (handlers: WakeEngineHandlers): WakeEngine => {
    let session: Session | null = null
    let closedByUs = false
    let ready = false

    return {
      async start() {
        const t = await options.getToken()
        if (t.token === MOCK_TOKEN) {
          // Mock mode: no cloud, no transcripts. The hotkey and the debug /wake endpoint still work.
          ready = true
          handlers.onReady()
          return
        }
        const ai = new GoogleGenAI({ apiKey: t.token, httpOptions: { apiVersion: options.apiVersion ?? 'v1alpha' } })
        session = await ai.live.connect({
          model: options.model ?? t.model ?? TRANSCRIBE_MODEL,
          config: {
            responseModalities: [Modality.TEXT],
            inputAudioTranscription: {
              languageCodes: [...(options.languageCodes ?? ['en-GB', 'en-US'])],
              ...(options.vocabulary?.length ? { customVocabulary: [...options.vocabulary] } : {}),
            },
          },
          callbacks: {
            onopen: () => {
              ready = true
              handlers.onReady()
            },
            onmessage: (msg: LiveServerMessage) => {
              if (msg.goAway) handlers.onGoAway?.()
              const sc = msg.serverContent
              if (!sc) return
              if (sc.interimInputTranscription?.text) handlers.onTranscript(sc.interimInputTranscription.text, false)
              if (sc.inputTranscription?.text) handlers.onTranscript(sc.inputTranscription.text, true)
            },
            onerror: (e: unknown) => handlers.onError(new Error(e instanceof Error ? e.message : String((e as { message?: string })?.message ?? e)), false),
            onclose: (e: unknown) => {
              ready = false
              if (!closedByUs) handlers.onError(new Error(`wake stream closed${(e as { reason?: string })?.reason ? `: ${(e as { reason?: string }).reason}` : ''}`), false)
            },
          },
        })
      },
      send(pcm) {
        if (!session || !ready) return
        try {
          session.sendRealtimeInput({ audio: { data: pcm16ToBase64(pcm), mimeType: 'audio/pcm;rate=16000' } })
        } catch (e) {
          handlers.onError(e instanceof Error ? e : new Error(String(e)), false)
        }
      },
      stop() {
        closedByUs = true
        ready = false
        try {
          session?.close()
        } catch {
          // already closed
        }
        session = null
      },
    }
  }
}
