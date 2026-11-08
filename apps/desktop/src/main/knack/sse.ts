// A small server-sent-events reader: bytes in, whole events out. Pure, so it can be tested without a connection. Follows the usual rules: lines end in LF, CRLF or CR; a blank line
// ends an event; "event:" names it, "data:" lines are joined with a line break; a line starting with ":" is a comment (a keep-alive) and says nothing.
export interface SseEvent {
  event: string
  data: string
}

export interface SseParser {
  /** Feeds the next text from the connection; returns the events it completed. */
  push(text: string): SseEvent[]
}

export function createSseParser(): SseParser {
  let buffer = ''
  let event = ''
  let data: string[] = []
  let sawField = false
  return {
    push(text) {
      buffer += text
      const out: SseEvent[] = []
      // Split on line ends, keeping an unfinished last line for the next push. A CR at the very end waits: it may be the first half of a CRLF.
      const lines = buffer.split(/\r\n|\n|\r(?!$)/)
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (line === '') {
          if (sawField) out.push({ event: event || 'message', data: data.join('\n') })
          event = ''
          data = []
          sawField = false
          continue
        }
        if (line.startsWith(':')) continue
        const i = line.indexOf(':')
        const field = i === -1 ? line : line.slice(0, i)
        const value = i === -1 ? '' : line.slice(i + 1).replace(/^ /, '')
        if (field === 'event') {
          event = value
          sawField = true
        } else if (field === 'data') {
          data.push(value)
          sawField = true
        }
      }
      return out
    },
  }
}
