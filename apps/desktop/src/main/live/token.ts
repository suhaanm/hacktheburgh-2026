// Short-lived ephemeral tokens for the Live websocket, minted in the MAIN process with the Gemini key from the environment.
//
//   POST https://generativelanguage.googleapis.com/v1beta/auth_tokens      header x-goog-api-key: <key>   (verified live, 7 Nov 2026)
//   body { uses: 1, expireTime, newSessionExpireTime, bidiGenerateContentSetup: { model: "models/<id>" } }  ->  { name: "auth_tokens/..." }
//
// The key travels in that one header and nowhere else: not in a URL, a log line, an error message, a renderer or a file. The token (not the
// key) is what the websocket uses, in an `Authorization: Token ...` header. The token is locked to the configured model, valid for one new
// session within a minute, and expires in ten minutes. Errors say what failed in plain words and never carry a body, a header or a URL.
import type { Env } from './flags'

export const AUTH_TOKENS_URL = 'https://generativelanguage.googleapis.com/v1beta/auth_tokens'
export const MODELS_URL = 'https://generativelanguage.googleapis.com/v1beta/models'
const TOKEN_RE = /^auth_tokens\/[A-Za-z0-9_\-+=/.]{8,400}$/

export type TokenFailure = 'no_key' | 'refused' | 'network' | 'bad_response'

export class TokenError extends Error {
  constructor(
    readonly code: TokenFailure,
    message: string,
  ) {
    super(message)
    this.name = 'TokenError'
  }
}

export interface LiveToken {
  token: string
  expiresAt: number
}

export interface TokenMinter {
  mint(model: string): Promise<LiveToken>
}

export interface MinterOptions {
  // How the token is tied to the model: 'model' locks the model id (the field mask names only it), 'none' leaves the token open. Default 'model'.
  lock?: 'model' | 'none' | 'setup'
  env?: Env
  fetchImpl?: typeof fetch
  now?: () => number
  url?: string
  timeoutMs?: number
}

const isLoopbackHttp = (u: string): boolean => /^http:\/\/(127\.0\.0\.1|localhost|\[::1\])(:\d+)?\//.test(u)

export function createTokenMinter(o: MinterOptions = {}): TokenMinter {
  const env = o.env ?? process.env
  const doFetch = o.fetchImpl ?? ((i, init) => fetch(i, init))
  const now = o.now ?? Date.now
  const url = o.url ?? AUTH_TOKENS_URL
  const lock = o.lock ?? 'model'
  if (!url.startsWith('https://') && !isLoopbackHttp(url)) throw new Error('the token service must be https (or a loopback test server)')
  return {
    async mint(model) {
      const key = (env.GEMINI_API_KEY ?? '').trim()
      if (!key) throw new TokenError('no_key', 'No Gemini key is configured, so voice is unavailable.')
      const t = now()
      const ctl = new AbortController()
      const timer = setTimeout(() => ctl.abort(), o.timeoutMs ?? 10_000)
      let res: Response
      try {
        res = await doFetch(url, {
          method: 'POST',
          headers: { 'x-goog-api-key': key, 'content-type': 'application/json' },
          body: JSON.stringify({
            uses: 1,
            expireTime: new Date(t + 10 * 60_000).toISOString(),
            newSessionExpireTime: new Date(t + 60_000).toISOString(),
            ...(lock === 'none' ? {} : { bidiGenerateContentSetup: { model: `models/${model}` } }),
            ...(lock === 'model' ? { fieldMask: 'model' } : {}),
          }),
          signal: ctl.signal,
        })
      } catch {
        throw new TokenError('network', 'The voice service could not be reached.')
      } finally {
        clearTimeout(timer)
      }
      if (res.status === 401 || res.status === 403 || res.status === 400 || res.status === 429) throw new TokenError('refused', `The voice service refused the request (HTTP ${res.status}).`)
      if (!res.ok) throw new TokenError('network', `The voice service failed (HTTP ${res.status}).`)
      let json: unknown
      try {
        json = await res.json()
      } catch {
        throw new TokenError('bad_response', 'The voice service sent something unexpected.')
      }
      const name = typeof json === 'object' && json !== null ? (json as Record<string, unknown>).name : undefined
      if (typeof name !== 'string' || !TOKEN_RE.test(name)) throw new TokenError('bad_response', 'The voice service sent something unexpected.')
      return { token: name, expiresAt: t + 10 * 60_000 }
    },
  }
}

export interface ModelCheck {
  ok: boolean
  reason: 'ok' | 'no_model' | 'no_key' | 'unknown_model' | 'cannot_stream' | 'unreachable'
}

/** The boot check for the configured Live model: it exists for this key and supports the Live (bidi) method. Never guesses an id. */
export async function checkLiveModel(model: string | null, o: MinterOptions = {}): Promise<ModelCheck> {
  const env = o.env ?? process.env
  if (!model) return { ok: false, reason: 'no_model' }
  const key = (env.GEMINI_API_KEY ?? '').trim()
  if (!key) return { ok: false, reason: 'no_key' }
  const doFetch = o.fetchImpl ?? ((i, init) => fetch(i, init))
  const base = o.url ?? MODELS_URL
  const ctl = new AbortController()
  const timer = setTimeout(() => ctl.abort(), o.timeoutMs ?? 8000)
  try {
    const res = await doFetch(`${base}/${encodeURIComponent(model)}`, { headers: { 'x-goog-api-key': key }, signal: ctl.signal })
    if (res.status === 404) return { ok: false, reason: 'unknown_model' }
    if (!res.ok) return { ok: false, reason: 'unreachable' }
    const json = (await res.json()) as { supportedGenerationMethods?: unknown }
    const methods = Array.isArray(json.supportedGenerationMethods) ? json.supportedGenerationMethods : []
    return methods.includes('bidiGenerateContent') ? { ok: true, reason: 'ok' } : { ok: false, reason: 'cannot_stream' }
  } catch {
    return { ok: false, reason: 'unreachable' }
  } finally {
    clearTimeout(timer)
  }
}

/**
 * The boot check for the app's models: the Gemini key is present and the service answers for a configured model (the accurate one, else the fast one, else
 * the live one). Only the key travels, in one header; nothing else is sent. The app used to run the old OpenAI check here, which can never pass with a Gemini
 * key, so every launch started with models off.
 */
export async function checkGeminiKey(o: MinterOptions = {}): Promise<{ ok: boolean; reason: 'ok' | 'no_key' | 'no_model' | 'unknown_model' | 'unreachable' }> {
  const env = o.env ?? process.env
  const key = (env.GEMINI_API_KEY ?? '').trim()
  if (!key) return { ok: false, reason: 'no_key' }
  const model = [env.GEMINI_MODEL_ACCURATE, env.GEMINI_MODEL_FAST, env.GEMINI_MODEL_LIVE, env.MODEL_LIVE].map((v) => (v ?? '').trim()).find((v) => v && /^[A-Za-z0-9._:-]+$/.test(v))
  if (!model) return { ok: false, reason: 'no_model' }
  const doFetch = o.fetchImpl ?? ((i, init) => fetch(i, init))
  const ctl = new AbortController()
  const timer = setTimeout(() => ctl.abort(), o.timeoutMs ?? 8000)
  try {
    const res = await doFetch(`${o.url ?? MODELS_URL}/${encodeURIComponent(model)}`, { headers: { 'x-goog-api-key': key }, signal: ctl.signal })
    if (res.status === 404) return { ok: false, reason: 'unknown_model' }
    return res.ok ? { ok: true, reason: 'ok' } : { ok: false, reason: 'unreachable' }
  } catch {
    return { ok: false, reason: 'unreachable' }
  } finally {
    clearTimeout(timer)
  }
}
