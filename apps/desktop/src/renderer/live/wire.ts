// Adapted from google-gemini/gemini-live-api-examples — gemini-live-ephemeral-tokens-websocket/frontend/geminilive.js
// (the repo has no LICENSE file; the hackathon guide points builders to it. See THIRD_PARTY_NOTICES.md)
//
// Pure protocol layer: message builders and a server-message parser. No DOM, no Electron, no shared-runtime imports,
// so it runs unchanged in the renderer, in vitest and in the Node smoke test.

export const LIVE_WS_BASE = 'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.'

export type LiveAuth = { kind: 'token'; value: string } | { kind: 'key'; value: string }

export function liveUrl(auth: LiveAuth): string {
  const q = encodeURIComponent(auth.value)
  return auth.kind === 'token'
    ? `${LIVE_WS_BASE}BidiGenerateContentConstrained?access_token=${q}`
    : `${LIVE_WS_BASE}BidiGenerateContent?key=${q}`
}

// ---------- outgoing ----------
export type Behavior = 'NON_BLOCKING' | 'BLOCKING'
export type Scheduling = 'SILENT' | 'WHEN_IDLE' | 'INTERRUPT'

export interface JsonSchema {
  type: string
  description?: string
  properties?: Record<string, JsonSchema>
  required?: string[]
  items?: JsonSchema
  enum?: string[]
  minItems?: number
  maxItems?: number
  minimum?: number
  maximum?: number
}

export interface FunctionDeclaration {
  name: string
  description: string
  parameters?: JsonSchema
  behavior?: Behavior
}

export interface VadConfig {
  startOfSpeechSensitivity?: 'START_SENSITIVITY_HIGH' | 'START_SENSITIVITY_LOW'
  endOfSpeechSensitivity?: 'END_SENSITIVITY_HIGH' | 'END_SENSITIVITY_LOW'
  prefixPaddingMs?: number
  silenceDurationMs?: number
}

export interface SetupOptions {
  model: string
  voiceName: string
  systemInstruction: string
  tools: FunctionDeclaration[]
  resumptionHandle?: string | null
  vad?: VadConfig
  // Only the server default (all video frames count towards the turn) lets the model always see the latest screen.
  turnCoverage?: 'TURN_INCLUDES_ONLY_ACTIVITY' | 'TURN_INCLUDES_AUDIO_ACTIVITY_AND_ALL_VIDEO'
  // Undefined = omit. gemini-3.8-live is fixed at MINIMAL thinking and rejects/ignores other levels.
  thinkingLevel?: 'MINIMAL'
  compressionTriggerTokens?: number
}

export function buildSetup(o: SetupOptions): { setup: Record<string, unknown> } {
  const generationConfig: Record<string, unknown> = {
    responseModalities: ['AUDIO'],
    speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: o.voiceName } } },
  }
  if (o.thinkingLevel) generationConfig.thinkingConfig = { thinkingLevel: o.thinkingLevel }
  const vad = o.vad ?? {}
  const realtimeInputConfig: Record<string, unknown> = {
    automaticActivityDetection: { disabled: false, ...vad },
    activityHandling: 'START_OF_ACTIVITY_INTERRUPTS',
  }
  if (o.turnCoverage) realtimeInputConfig.turnCoverage = o.turnCoverage
  const compression: Record<string, unknown> = { slidingWindow: {} }
  if (o.compressionTriggerTokens) compression.triggerTokens = o.compressionTriggerTokens
  return {
    setup: {
      model: `models/${o.model}`,
      generationConfig,
      systemInstruction: { parts: [{ text: o.systemInstruction }] },
      tools: o.tools.length ? [{ functionDeclarations: o.tools }] : undefined,
      realtimeInputConfig,
      // Both ON from the first byte: A/V sessions die at ~2 min without compression, connections at ~10 min without resumption.
      contextWindowCompression: compression,
      sessionResumption: o.resumptionHandle ? { handle: o.resumptionHandle } : {},
      inputAudioTranscription: {},
      outputAudioTranscription: {},
    },
  }
}

export interface FunctionResponse {
  id: string
  name: string
  response: Record<string, unknown>
  // Top-level sibling of `response` (verified against @google/genai 2.32 FunctionResponse), NOT inside `response`.
  scheduling?: Scheduling
}

export const msg = {
  audio: (base64Pcm16: string, rate = 16000) => ({ realtimeInput: { audio: { data: base64Pcm16, mimeType: `audio/pcm;rate=${rate}` } } }),
  video: (base64: string, mimeType = 'image/jpeg') => ({ realtimeInput: { video: { data: base64, mimeType } } }),
  text: (text: string) => ({ realtimeInput: { text } }),
  audioStreamEnd: () => ({ realtimeInput: { audioStreamEnd: true } }),
  clientContent: (text: string, turnComplete: boolean) => ({
    clientContent: { turns: [{ role: 'user', parts: [{ text }] }], turnComplete },
  }),
  toolResponse: (functionResponses: FunctionResponse[]) => ({ toolResponse: { functionResponses } }),
}

// ---------- incoming ----------
export interface FunctionCall {
  id: string
  name: string
  args: Record<string, unknown>
}

export type LiveServerEvent =
  | { type: 'setupComplete' }
  | { type: 'audio'; base64: string; mimeType?: string }
  | { type: 'text'; text: string }
  | { type: 'inputTranscription'; text: string; finished: boolean }
  | { type: 'interimInputTranscription'; text: string }
  | { type: 'outputTranscription'; text: string; finished: boolean }
  | { type: 'interrupted' }
  | { type: 'generationComplete' }
  | { type: 'turnComplete'; interactionStatus?: string }
  | { type: 'waitingForInput' }
  | { type: 'toolCall'; calls: FunctionCall[] }
  | { type: 'toolCallCancellation'; ids: string[] }
  | { type: 'goAway'; timeLeftMs: number }
  | { type: 'resumptionUpdate'; handle: string | null; resumable: boolean }
  | { type: 'voiceActivity'; activity: 'start' | 'end' | 'unknown' }
  | { type: 'usage'; totalTokens: number | null }

type Json = Record<string, unknown>
const isObj = (v: unknown): v is Json => typeof v === 'object' && v !== null
const str = (v: unknown): string | undefined => (typeof v === 'string' ? v : undefined)

// protobuf Duration arrives as "12s" / "0.5s" (or {seconds,nanos}).
export function parseDurationMs(v: unknown): number {
  if (typeof v === 'string') {
    const n = Number.parseFloat(v)
    return Number.isFinite(n) ? Math.round(n * 1000) : 0
  }
  if (isObj(v)) {
    const s = Number(v.seconds ?? 0)
    const ns = Number(v.nanos ?? 0)
    return Math.round(s * 1000 + ns / 1e6)
  }
  return 0
}

// One server message can bundle several fields (audio + transcription + turnComplete ...): every field is processed.
// Order matters downstream: transcription/audio before interrupted/turnComplete.
export function parseServerMessage(data: unknown): LiveServerEvent[] {
  const out: LiveServerEvent[] = []
  if (!isObj(data)) return out

  if (data.setupComplete !== undefined) out.push({ type: 'setupComplete' })

  const sc = isObj(data.serverContent) ? data.serverContent : undefined
  if (sc) {
    const turn = isObj(sc.modelTurn) ? sc.modelTurn : undefined
    const parts = Array.isArray(turn?.parts) ? (turn.parts as unknown[]) : []
    for (const p of parts) {
      if (!isObj(p)) continue
      const inline = isObj(p.inlineData) ? p.inlineData : undefined
      if (inline && typeof inline.data === 'string') out.push({ type: 'audio', base64: inline.data, mimeType: str(inline.mimeType) })
      else if (typeof p.text === 'string' && p.text) out.push({ type: 'text', text: p.text })
    }
    if (isObj(sc.inputTranscription)) {
      out.push({ type: 'inputTranscription', text: str(sc.inputTranscription.text) ?? '', finished: sc.inputTranscription.finished === true })
    }
    if (isObj(sc.interimInputTranscription)) {
      out.push({ type: 'interimInputTranscription', text: str(sc.interimInputTranscription.text) ?? '' })
    }
    if (isObj(sc.outputTranscription)) {
      out.push({ type: 'outputTranscription', text: str(sc.outputTranscription.text) ?? '', finished: sc.outputTranscription.finished === true })
    }
    if (sc.interrupted === true) out.push({ type: 'interrupted' })
    if (sc.generationComplete === true) out.push({ type: 'generationComplete' })
    if (sc.waitingForInput === true) out.push({ type: 'waitingForInput' })
    if (sc.turnComplete === true) {
      const status = str(sc.interactionStatus) ?? str(data.interactionStatus)
      out.push({ type: 'turnComplete', interactionStatus: status })
    }
    // Some docs place cancellation inside serverContent; the API reference puts it at top level. Accept both.
    if (isObj(sc.toolCallCancellation) && Array.isArray(sc.toolCallCancellation.ids)) {
      out.push({ type: 'toolCallCancellation', ids: (sc.toolCallCancellation.ids as unknown[]).filter((i): i is string => typeof i === 'string') })
    }
  }

  if (isObj(data.toolCall) && Array.isArray(data.toolCall.functionCalls)) {
    const calls: FunctionCall[] = []
    for (const fc of data.toolCall.functionCalls as unknown[]) {
      if (!isObj(fc) || typeof fc.name !== 'string') continue
      calls.push({ id: str(fc.id) ?? `${fc.name}-${Date.now()}-${calls.length}`, name: fc.name, args: isObj(fc.args) ? fc.args : {} })
    }
    if (calls.length) out.push({ type: 'toolCall', calls })
  }
  if (isObj(data.toolCallCancellation) && Array.isArray(data.toolCallCancellation.ids)) {
    out.push({ type: 'toolCallCancellation', ids: (data.toolCallCancellation.ids as unknown[]).filter((i): i is string => typeof i === 'string') })
  }
  if (isObj(data.goAway)) out.push({ type: 'goAway', timeLeftMs: parseDurationMs(data.goAway.timeLeft) })
  if (isObj(data.sessionResumptionUpdate)) {
    const u = data.sessionResumptionUpdate
    const handle = str(u.newHandle) ?? str(u.token) ?? null
    out.push({ type: 'resumptionUpdate', handle: handle || null, resumable: u.resumable === true && !!handle })
  }
  if (isObj(data.voiceActivity)) {
    const t = str(data.voiceActivity.type)
    out.push({ type: 'voiceActivity', activity: t === 'ACTIVITY_START' ? 'start' : t === 'ACTIVITY_END' ? 'end' : 'unknown' })
  }
  if (isObj(data.usageMetadata)) {
    const n = data.usageMetadata.totalTokenCount
    out.push({ type: 'usage', totalTokens: typeof n === 'number' ? n : null })
  }
  // interactionStatus is documented both inside serverContent (always with turnComplete) and top level.
  return out
}

export function decodeFrame(data: unknown): unknown {
  let text: string | undefined
  if (typeof data === 'string') text = data
  else if (data instanceof ArrayBuffer) text = new TextDecoder().decode(data)
  else if (ArrayBuffer.isView(data)) text = new TextDecoder().decode(data as ArrayBufferView)
  if (text === undefined) return undefined
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

// ---------- base64 <-> PCM16 (no Buffer: runs in the renderer) ----------
export function bytesToBase64(bytes: Uint8Array): string {
  let bin = ''
  const CHUNK = 0x8000
  for (let i = 0; i < bytes.length; i += CHUNK) bin += String.fromCharCode(...bytes.subarray(i, i + CHUNK))
  return btoa(bin)
}

export function base64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64)
  const out = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i)
  return out
}

export function floatToPcm16Base64(f32: Float32Array): string {
  const i16 = new Int16Array(f32.length)
  for (let i = 0; i < f32.length; i++) {
    const s = Math.max(-1, Math.min(1, f32[i]!))
    i16[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return bytesToBase64(new Uint8Array(i16.buffer))
}

// Splits PCM16 samples into base64 chunks (default 100 ms @ 16 kHz) for sending pre-roll audio.
export function pcm16ToBase64Chunks(pcm: Int16Array, samplesPerChunk = 1600): string[] {
  const out: string[] = []
  for (let i = 0; i < pcm.length; i += samplesPerChunk) {
    const part = pcm.subarray(i, Math.min(pcm.length, i + samplesPerChunk))
    out.push(bytesToBase64(new Uint8Array(part.buffer, part.byteOffset, part.byteLength)))
  }
  return out
}
