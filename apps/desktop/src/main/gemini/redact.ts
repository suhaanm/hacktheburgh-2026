// Log hygiene: nothing that reaches a log may contain the API key, a screenshot, or long message text.
// ARCH: wrap ctx.log with `redactingLog` in src/main/index.ts so every lane gets this, not just the Gemini services.

const PATTERNS: Array<[RegExp, string]> = [
  [/data:[a-z]+\/[a-z0-9.+-]+;base64,[A-Za-z0-9+/=_-]+/gi, '<redacted image>'],
  [/AIza[0-9A-Za-z_-]{16,}/g, '<redacted key>'],
  [/(x-goog-api-key["']?\s*[:=]\s*["']?)[^\s"',;&]+/gi, '$1<redacted key>'],
  [/([?&](?:key|api[_-]?key|access_token|token)=)[^\s&"']+/gi, '$1<redacted>'],
  [/\b(Bearer\s+)[A-Za-z0-9._~+/-]{10,}/gi, '$1<redacted>'],
  [/(auth_tokens?\/)[A-Za-z0-9._~+/-]{10,}/gi, '$1<redacted>'],
  // Anything that looks like a base64 blob (screenshots, audio): long unbroken runs of base64 characters.
  [/[A-Za-z0-9+/_-]{120,}={0,2}/g, '<redacted blob>'],
]

const MAX_ARG_CHARS = 300

export function redactText(text: string): string {
  let out = text
  for (const [re, replacement] of PATTERNS) out = out.replace(re, replacement)
  return out
}

function stringify(arg: unknown): string {
  if (typeof arg === 'string') return arg
  if (arg instanceof Error) return `${arg.name}: ${arg.message}`
  try {
    return JSON.stringify(arg) ?? String(arg)
  } catch {
    return String(arg)
  }
}

/** One log argument -> a short, redacted string. Long values are cut so message text cannot leak whole. */
export function redactArg(arg: unknown): string {
  const text = redactText(stringify(arg))
  return text.length > MAX_ARG_CHARS ? `${text.slice(0, MAX_ARG_CHARS)}…(${text.length - MAX_ARG_CHARS} more chars cut)` : text
}

export type LogFn = (scope: string, ...args: unknown[]) => void

export function redactingLog(log: LogFn): LogFn {
  return (scope, ...args) => log(scope, ...args.map(redactArg))
}
