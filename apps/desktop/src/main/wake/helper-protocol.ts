// What the Hey Knack listener may say on its stdout, and how this side reads it. The line format is CLOSED: three events, one optional code from
// a fixed list, no other field. A line with anything else (a transcript, a path, a number we did not expect) is a protocol violation: the line is
// dropped unread, and the supervisor stops the helper. This is the second lock on "no transcript ever leaves the helper": the helper does not
// print text, and if a changed or replaced helper tried to, this parser would refuse it.

export const HELPER_ERROR_CODES = [
  'mic_denied', 'mic_restricted', 'speech_denied', 'speech_restricted', 'on_device_unavailable', 'locale_unsupported',
  'recognizer_unavailable', 'audio_engine_failed', 'no_input_device', 'internal',
] as const
export type HelperErrorCode = (typeof HELPER_ERROR_CODES)[number]

/** A failure the worker has to fix (a permission, no on-device recogniser): the helper is not started again by itself. */
export const FINAL_CODES: ReadonlySet<HelperErrorCode> = new Set<HelperErrorCode>(['mic_denied', 'mic_restricted', 'speech_denied', 'speech_restricted', 'on_device_unavailable', 'locale_unsupported'])

export type HelperEvent = { event: 'ready' } | { event: 'heard' } | { event: 'error'; code: HelperErrorCode }
export type ParseFailure = 'too_long' | 'not_json' | 'not_an_object' | 'unknown_event' | 'extra_fields' | 'bad_code'
export type ParsedLine = { ok: true; event: HelperEvent } | { ok: false; reason: ParseFailure }

export const MAX_LINE_BYTES = 200

export function parseHelperLine(line: string): ParsedLine {
  if (line.length > MAX_LINE_BYTES) return { ok: false, reason: 'too_long' }
  let v: unknown
  try {
    v = JSON.parse(line)
  } catch {
    return { ok: false, reason: 'not_json' }
  }
  if (typeof v !== 'object' || v === null || Array.isArray(v)) return { ok: false, reason: 'not_an_object' }
  const o = v as Record<string, unknown>
  const keys = Object.keys(o)
  if (o.event === 'ready' || o.event === 'heard') return keys.length === 1 ? { ok: true, event: { event: o.event } } : { ok: false, reason: 'extra_fields' }
  if (o.event === 'error') {
    if (keys.length !== 2 || !('code' in o)) return { ok: false, reason: 'extra_fields' }
    return (HELPER_ERROR_CODES as readonly unknown[]).includes(o.code) ? { ok: true, event: { event: 'error', code: o.code as HelperErrorCode } } : { ok: false, reason: 'bad_code' }
  }
  return { ok: false, reason: 'unknown_event' }
}

/** Splits a byte stream into lines. A line longer than the cap is dropped whole and reported as `overflow`, so memory stays bounded. */
export function createLineSplitter(maxLine = MAX_LINE_BYTES): { push(chunk: string): { lines: string[]; overflow: boolean } } {
  let buf = ''
  let skipping = false
  return {
    push(chunk) {
      const lines: string[] = []
      let overflow = false
      for (const ch of chunk) {
        if (ch === '\n') {
          if (skipping) skipping = false
          else if (buf.length > 0) lines.push(buf)
          buf = ''
        } else if (!skipping) {
          buf += ch
          if (buf.length > maxLine) {
            skipping = true
            overflow = true
            buf = ''
          }
        }
      }
      return { lines, overflow }
    },
  }
}
