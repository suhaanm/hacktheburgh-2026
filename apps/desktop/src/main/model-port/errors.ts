// Errors from the model port. Codes are coarse on purpose; what a person hears is `plainByCode` (no codes, no blame, no guessing).

export type ModelErrorCode = 'timeout' | 'api' | 'parse' | 'empty' | 'no_input' | 'auth' | 'rate_limit' | 'network' | 'config' | 'refusal' | 'blocked'

const PLAIN: Record<ModelErrorCode, string> = {
  auth: "I can't use my online helper because it isn't set up yet.",
  config: "I can't use my online helper because a model name is missing from its setup.",
  rate_limit: "I'm getting too many requests right now. Please try again in a moment.",
  network: "I can't reach the internet right now.",
  timeout: 'That is taking too long.',
  parse: 'I got a muddled answer and did not trust it.',
  empty: 'I did not get an answer.',
  refusal: 'My online helper declined to answer that.',
  blocked: 'The old online helpers are switched off, or a privacy check stopped this, so nothing was sent.',
  no_input: 'There was nothing to look at.',
  api: 'Something went wrong on my side.',
}

export const plainByCode = (code: string): string => PLAIN[code as ModelErrorCode] ?? PLAIN.api

export class ModelPortError extends Error {
  constructor(
    public readonly code: ModelErrorCode,
    message: string,
    public readonly status?: number,
  ) {
    super(message)
    this.name = 'ModelPortError'
  }
  get userMessage(): string {
    return plainByCode(this.code)
  }
}

/** Plain-English line for any thrown value. */
export const plainFailure = (e: unknown): string => (e instanceof ModelPortError ? e.userMessage : PLAIN.api)

/** Failures where saying exactly what is wrong helps (and is safe); the rest stay generic. */
export const isEnvironmental = (e: unknown): boolean =>
  e instanceof ModelPortError && (e.code === 'auth' || e.code === 'network' || e.code === 'rate_limit' || e.code === 'config')
