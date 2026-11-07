// Agents never show raw errors to the user: every failure becomes one plain-English sentence.

/** An error whose message is already written for the user. */
export class AgentUserError extends Error {
  constructor(
    readonly userMessage: string,
    readonly code: 'user' | 'busy' | 'bad_request' = 'user',
  ) {
    super(userMessage)
    this.name = 'AgentUserError'
  }
}

export class AgentTimeoutError extends Error {
  constructor() {
    super('agent timed out')
    this.name = 'AgentTimeoutError'
  }
}

export class AgentCancelledError extends Error {
  constructor() {
    super('agent cancelled')
    this.name = 'AgentCancelledError'
  }
}

const KEY_PATTERN = /AIza[0-9A-Za-z_-]{20,}|(api[_-]?key|token)=[^\s&]+/gi

export function redactForLog(text: string): string {
  return text.replace(KEY_PATTERN, '[redacted]')
}

export const TIMEOUT_MESSAGE = 'That took too long, so I stopped. Nothing was sent or changed. Please ask me again.'
export const GENERIC_MESSAGE = 'Something went wrong while I was working on that. Nothing was sent or changed.'

export function toPlainMessage(err: unknown): string {
  if (err instanceof AgentUserError) return err.userMessage
  if (err instanceof AgentTimeoutError) return TIMEOUT_MESSAGE
  const detail = err instanceof Error ? `${err.name} ${err.message}` : String(err)
  const status = typeof err === 'object' && err !== null && 'status' in err ? String((err as { status: unknown }).status) : ''
  const probe = `${detail} ${status}`
  if (/\b429\b|quota|rate.?limit|RESOURCE_EXHAUSTED/i.test(probe)) {
    return 'My checking service is busy at the moment. Please try again in a minute.'
  }
  if (/\b40[13]\b|api key|PERMISSION_DENIED|UNAUTHENTICATED/i.test(probe)) {
    return 'I cannot reach my checking service right now. Please ask whoever set me up to look at my settings.'
  }
  if (/ENOTFOUND|ECONNRE|ETIMEDOUT|EAI_AGAIN|fetch failed|network|socket/i.test(probe)) {
    return 'I could not get online just now. Please check your internet and try again.'
  }
  if (/abort/i.test(probe)) return TIMEOUT_MESSAGE
  return GENERIC_MESSAGE
}

export function logAgentError(kind: string, err: unknown): void {
  const detail = err instanceof Error ? `${err.name}: ${err.message}` : String(err)
  console.error(`[agents] ${kind} failed: ${redactForLog(detail).slice(0, 300)}`)
}
