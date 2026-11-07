// The two voice hooks Cue calls (their interfaces are defined by the Cue module in main/cue/voice.ts; this file implements them).
//
//   CueVoice.listenOnce(options)   hear one spoken answer to the question card. The microphone opens ONLY if the worker presses the talk key
//                                  inside the listening window; it never opens before the call and is released when the call resolves.
//   CueSpeaker.say(lineId)         speak one fixed pack line (ElevenLabs, cached by the agent service). By line ID only: the agent refuses
//                                  free text, and so does this file. Never over a Gemini Live utterance, and cut at once when the worker
//                                  presses the talk key.
//
// Both are inert unless the Live flags are on and the worker opted in; the speaker also needs UNDERSTUDY_VOICE=1. Neither throws.
import type { CueSpeaker, CueVoice, VoiceOption } from '../cue/voice'
import { OTHER_OPTION_ID, matchSpokenOption } from '../cue/voice'
import { liveFlagOn, speakerFlagOn, type Env } from './flags'
import type { LiveManager } from './manager'
import type { ClipPlayer } from './ports'

export const DEFAULT_LISTEN_MS = 6000

export interface CueVoiceDeps {
  manager: Pick<LiveManager, 'listen' | 'voiceAllowed'>
  // The worker's own Cue switch (cueVoice in settings). Cue checks it too; this is the second look.
  cueVoiceOn?: () => boolean
}

/** Matches with the shared matcher so "the second one" means the same thing everywhere. Ambiguous is null, never a guess. */
export function createCueVoice(d: CueVoiceDeps): CueVoice {
  return {
    async listenOnce(options: readonly VoiceOption[], opts?: { timeoutMs?: number }): Promise<string | null> {
      try {
        if (options.length === 0 || d.cueVoiceOn?.() === false || !d.manager.voiceAllowed()) return null
        const heard = await d.manager.listen(opts?.timeoutMs ?? DEFAULT_LISTEN_MS)
        if (!heard) return null
        const id = matchSpokenOption(heard, options)
        // Only a known option id or the fixed "something else" id can leave this function.
        return id !== null && (id === OTHER_OPTION_ID || options.some((o) => o.id === id)) ? id : null
      } catch {
        return null
      }
    },
  }
}

// ------------------------------------------------------------------------------------------------ the speaker
export const LINE_ID_RE = /^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$/
const SILENT_SOURCES = new Set(['disabled', 'mock', 'silent', 'timeout', 'error', 'personal_data'])

export interface SpeakerDeps {
  env?: Env
  agentUrl: string
  isLoopback: (url: string) => boolean
  clip: ClipPlayer
  fetchImpl?: typeof fetch
  // True while a Live conversation is open or its key is down: a clip never overlaps it.
  liveBusy: () => boolean
  cueVoiceOn?: () => boolean
  timeoutMs?: number
}

export interface LineSpeaker extends CueSpeaker {
  /** Cue registers the engine's whisper id and text before saying it. The text is not sent anywhere: only the id is. */
  registerLine(id: string, text: string): void
  stop(): void
}

export function createCueSpeaker(d: SpeakerDeps): LineSpeaker {
  const env = d.env ?? process.env
  if (!d.isLoopback(d.agentUrl)) throw new Error('the voice service must be on this machine (127.0.0.1)')
  const doFetch = d.fetchImpl ?? ((i, init) => fetch(i, init))
  const known = new Set<string>()
  let epoch = 0
  return {
    registerLine(id) {
      if (LINE_ID_RE.test(id) && id.length <= 90) known.add(id)
    },
    stop() {
      epoch += 1
      d.clip.stop()
    },
    async say(lineId: string): Promise<void> {
      try {
        if (!liveFlagOn(env) || !speakerFlagOn(env) || d.cueVoiceOn?.() === false || d.liveBusy()) return
        // A line is spoken by id. Anything that is not a line id (a sentence, a path) is not spoken: the agent would refuse it anyway.
        if (typeof lineId !== 'string' || !LINE_ID_RE.test(lineId) || lineId.length > 90) return
        const my = ++epoch
        const ctl = new AbortController()
        const timer = setTimeout(() => ctl.abort(), d.timeoutMs ?? 4000)
        let res: Response
        try {
          res = await doFetch(`${d.agentUrl.replace(/\/+$/, '')}/voice/speak`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ line_id: lineId }), signal: ctl.signal })
        } finally {
          clearTimeout(timer)
        }
        if (!res.ok) return
        const source = res.headers.get('x-voice-source') ?? ''
        if (SILENT_SOURCES.has(source)) return
        const mime = res.headers.get('content-type') ?? ''
        if (!/^audio\//.test(mime)) return
        const bytes = new Uint8Array(await res.arrayBuffer())
        // The worker pressed the talk key, or a conversation opened, while the clip was on its way: do not play it.
        if (my !== epoch || d.liveBusy() || bytes.length === 0) return
        await d.clip.play(bytes, mime)
      } catch {
        /* a line that cannot be spoken is just not spoken */
      }
    },
  }
}
