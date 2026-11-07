// Adapted from google-gemini/gemini-live-api-examples — gemini-live-ephemeral-tokens-websocket/frontend/geminilive.js
// (the repo has no LICENSE file; the hackathon guide points builders to it. See THIRD_PARTY_NOTICES.md.) The message shapes were
// re-verified against the live service on 7 Nov 2026 (see docs/LIVE.md): setup, realtimeInput audio / video / text / activity,
// toolResponse, serverContent, toolCall, usageMetadata with per-modality token details.
//
// Pure protocol layer for the MAIN process: message builders and a server-message parser. No Electron, no DOM, no timers, no key.
// The websocket URL carries NO credential: the ephemeral token travels in the `Authorization: Token ...` header (verified to work on
// the constrained endpoint), so it can never end up in a URL, a log line or a crash report.

export const LIVE_WS_BASE = 'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.'
export const LIVE_ENDPOINT_URL = `${LIVE_WS_BASE}BidiGenerateContentConstrained`

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
  maxLength?: number
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

// 'vad': the server detects the end of speech (what the old Alongside code verified). 'manual': the client marks the start and end of
// each push-to-talk turn with activityStart / activityEnd and the server's detector is off.
export type TurnMode = 'vad' | 'manual'

export interface SetupOptions {
  model: string
  voiceName: string
  systemInstruction: string
  tools: FunctionDeclaration[]
  resumptionHandle?: string | null
  turnMode?: TurnMode
  vad?: VadConfig
  // A transcription-only turn (Cue's listenOnce): no tools, transcripts of what the worker said, the model's answer is discarded.
  transcribeOnly?: boolean
  // With a dedicated transcription model the answer is text, not audio.
  textOnly?: boolean
  // Keep the provider's running context small: compress when it reaches this many tokens, down to about the target.
  compressionTriggerTokens?: number
  compressionTargetTokens?: number
  // Ask the server for a transcript of what the worker said. Only Cue's one-answer turn needs it; a conversation asks for none, so no
  // transcript of either side ever arrives (nothing to keep, nothing to leak).
  inputTranscript?: boolean
}

export function buildSetup(o: SetupOptions): { setup: Record<string, unknown> } {
  // thinkingConfig is deliberately absent: gemini-3.8-live rejects it (the socket closes with 1007), verified by the old LIVE role.
  const generationConfig: Record<string, unknown> = o.textOnly
    ? { responseModalities: ['TEXT'] }
    : { responseModalities: ['AUDIO'], speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: o.voiceName } } } }
  const manual = o.turnMode === 'manual'
  const realtimeInputConfig: Record<string, unknown> = {
    automaticActivityDetection: manual ? { disabled: true } : { disabled: false, ...(o.vad ?? { startOfSpeechSensitivity: 'START_SENSITIVITY_LOW' }) },
    activityHandling: 'START_OF_ACTIVITY_INTERRUPTS',
  }
  return {
    setup: {
      model: `models/${o.model}`,
      generationConfig,
      systemInstruction: { parts: [{ text: o.systemInstruction }] },
      tools: !o.transcribeOnly && o.tools.length ? [{ functionDeclarations: o.tools }] : undefined,
      realtimeInputConfig,
      // A voice turn here is at most five minutes, so compression is a safety net; resumption covers a dropped socket.
      contextWindowCompression: {
        ...(o.compressionTriggerTokens ? { triggerTokens: o.compressionTriggerTokens } : {}),
        slidingWindow: o.compressionTargetTokens ? { targetTokens: o.compressionTargetTokens } : {},
      },
      sessionResumption: o.resumptionHandle ? { handle: o.resumptionHandle } : {},
      ...(o.inputTranscript ? { inputAudioTranscription: {} } : {}),
    },
  }
}

export interface FunctionResponse {
  id: string
  name: string
  response: Record<string, unknown>
  // A top-level sibling of `response`, not inside it (verified).
  scheduling?: Scheduling
}

export const msg = {
  audio: (base64Pcm16: string, rate = 16000) => ({ realtimeInput: { audio: { data: base64Pcm16, mimeType: `audio/pcm;rate=${rate}` } } }),
  video: (base64: string, mimeType = 'image/jpeg') => ({ realtimeInput: { video: { data: base64, mimeType } } }),
  text: (text: string) => ({ realtimeInput: { text } }),
  audioStreamEnd: () => ({ realtimeInput: { audioStreamEnd: true } }),
  activityStart: () => ({ realtimeInput: { activityStart: {} } }),
  activityEnd: () => ({ realtimeInput: { activityEnd: {} } }),
  toolResponse: (functionResponses: FunctionResponse[]) => ({ toolResponse: { functionResponses } }),
}

// ---------- incoming ----------
export interface FunctionCall {
  id: string
  name: string
  args: Record<string, unknown>
}

export interface TokenDetail {
  modality: string
  tokenCount: number
}

export interface UsageReport {
  promptTokens: number | null
  responseTokens: number | null
  totalTokens: number | null
  thoughtsTokens: number | null
  promptDetails: TokenDetail[]
  responseDetails: TokenDetail[]
}

export type LiveServerEvent =
  | { type: 'setupComplete' }
  | { type: 'audio'; base64: string; mimeType?: string }
  | { type: 'text'; text: string }
  | { type: 'inputTranscription'; text: string; finished: boolean }
  | { type: 'outputTranscription'; text: string; finished: boolean }
  | { type: 'interrupted' }
  | { type: 'generationComplete' }
  | { type: 'turnComplete' }
  | { type: 'toolCall'; calls: FunctionCall[] }
  | { type: 'toolCallCancellation'; ids: string[] }
  | { type: 'goAway'; timeLeftMs: number }
  | { type: 'resumptionUpdate'; handle: string | null; resumable: boolean }
  | { type: 'usage'; usage: UsageReport }

type Json = Record<string, unknown>
const isObj = (v: unknown): v is Json => typeof v === 'object' && v !== null && !Array.isArray(v)
const str = (v: unknown): string | undefined => (typeof v === 'string' ? v : undefined)
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : null)

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

function details(v: unknown): TokenDetail[] {
  if (!Array.isArray(v)) return []
  const out: TokenDetail[] = []
  for (const d of v) {
    if (!isObj(d)) continue
    const modality = str(d.modality)
    const n = num(d.tokenCount)
    if (modality && /^[A-Z_]{2,20}$/.test(modality) && n !== null) out.push({ modality, tokenCount: n })
  }
  return out
}

export function parseUsage(u: unknown): UsageReport | null {
  if (!isObj(u)) return null
  return {
    promptTokens: num(u.promptTokenCount),
    responseTokens: num(u.responseTokenCount),
    totalTokens: num(u.totalTokenCount),
    thoughtsTokens: num(u.thoughtsTokenCount),
    promptDetails: details(u.promptTokensDetails),
    responseDetails: details(u.responseTokensDetails),
  }
}

// One server message can bundle several fields (audio + transcription + turnComplete ...): every field is processed, in an order that
// matters downstream (transcription and audio before interrupted and turnComplete).
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
    if (isObj(sc.inputTranscription)) out.push({ type: 'inputTranscription', text: str(sc.inputTranscription.text) ?? '', finished: sc.inputTranscription.finished === true })
    if (isObj(sc.outputTranscription)) out.push({ type: 'outputTranscription', text: str(sc.outputTranscription.text) ?? '', finished: sc.outputTranscription.finished === true })
    if (sc.interrupted === true) out.push({ type: 'interrupted' })
    if (sc.generationComplete === true) out.push({ type: 'generationComplete' })
    if (sc.turnComplete === true) out.push({ type: 'turnComplete' })
    if (isObj(sc.toolCallCancellation) && Array.isArray(sc.toolCallCancellation.ids)) {
      out.push({ type: 'toolCallCancellation', ids: (sc.toolCallCancellation.ids as unknown[]).filter((i): i is string => typeof i === 'string') })
    }
  }
  if (isObj(data.toolCall) && Array.isArray(data.toolCall.functionCalls)) {
    const calls: FunctionCall[] = []
    for (const fc of data.toolCall.functionCalls as unknown[]) {
      if (!isObj(fc) || typeof fc.name !== 'string') continue
      calls.push({ id: str(fc.id) ?? `${fc.name}-${calls.length}`, name: fc.name, args: isObj(fc.args) ? fc.args : {} })
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
  const usage = parseUsage(data.usageMetadata)
  if (usage) out.push({ type: 'usage', usage })
  return out
}

export function decodeFrame(data: unknown): unknown {
  let text: string | undefined
  if (typeof data === 'string') text = data
  else if (data instanceof ArrayBuffer) text = new TextDecoder().decode(data)
  else if (ArrayBuffer.isView(data)) text = new TextDecoder().decode(new Uint8Array(data.buffer as ArrayBuffer, data.byteOffset, data.byteLength)) // a view over the same bytes, typed for TextDecoder
  else if (typeof Buffer !== 'undefined' && Buffer.isBuffer(data)) text = data.toString('utf8')
  if (text === undefined) return undefined
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

// ---------- base64 <-> PCM16 (main has Buffer) ----------
export const pcmBytesToBase64 = (bytes: Uint8Array): string => Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength).toString('base64')
export const base64ToBytes = (b64: string): Uint8Array => new Uint8Array(Buffer.from(b64, 'base64'))

/** Seconds of 16-bit mono PCM in a base64 chunk. */
export function pcmSeconds(base64: string, rate: number): number {
  // base64 length -> bytes without decoding: 3 bytes per 4 characters, minus padding.
  const pad = base64.endsWith('==') ? 2 : base64.endsWith('=') ? 1 : 0
  const bytes = Math.max(0, Math.floor((base64.length * 3) / 4) - pad)
  return bytes / 2 / rate
}

/** A base64 chunk of silence of `ms` milliseconds (16 kHz mono PCM16). */
export function silenceBase64(ms: number, rate = 16000): string {
  return Buffer.alloc(Math.max(0, Math.round((ms / 1000) * rate)) * 2).toString('base64')
}
