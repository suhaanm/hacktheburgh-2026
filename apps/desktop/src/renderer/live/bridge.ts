// The renderer's whole part in the NEW voice path: it owns the microphone and the speaker (getUserMedia and audio output exist only in a
// renderer) and does exactly what main tells it over the narrow bridge in main/live/preload-api.ts:
//
//   mic start / stop   open or release the microphone; every 32 ms chunk goes to main. The renderer never decides to listen.
//   audio play / flush play the model's audio (24 kHz PCM) and say when the queue drained.
//   clip play / stop   play one short fixed pack line (mp3 or wav).
//
// It holds no key and no token, opens no websocket, reads no screen, writes nothing to disk, and keeps no transcript (it never sees one).
// The old Alongside session code in this folder (LiveSession, connection, tools) is not used by this path.
import type { LiveRendererApi } from '../../main/live/preload-api'
import { AudioPlayer, MicCapture } from './audio'
import type { AudioInput, AudioOutput } from './types'

declare global {
  interface Window {
    understudyLive?: LiveRendererApi
  }
}

export interface BridgeDeps {
  createMic?: () => AudioInput
  createPlayer?: () => AudioOutput
  // Plays a clip and resolves when it ended. Default: an <audio> element on a Blob URL.
  playClip?: (bytes: ArrayBuffer, mime: string) => { done: Promise<boolean>; stop: () => void }
}

const defaultPlayClip: NonNullable<BridgeDeps['playClip']> = (bytes, mime) => {
  const url = URL.createObjectURL(new Blob([bytes], { type: mime }))
  const el = new Audio(url)
  const done = new Promise<boolean>((resolve) => {
    el.onended = () => resolve(true)
    el.onerror = () => resolve(false)
    void el.play().catch(() => resolve(false))
  }).finally(() => URL.revokeObjectURL(url))
  return {
    done,
    stop: () => {
      el.pause()
      el.src = ''
    },
  }
}

function isPermissionError(err: unknown): boolean {
  const name = err instanceof Error ? err.name : ''
  return /NotAllowed|Security|Permission/i.test(name) || /permission|denied/i.test(err instanceof Error ? err.message : '')
}

/** Starts the bridge; returns a stop function. A no-op (returns a no-op stop) when the page has no bridge, so the flag-off build is untouched. */
export function startLiveBridge(api: LiveRendererApi | undefined = typeof window !== 'undefined' ? window.understudyLive : undefined, deps: BridgeDeps = {}): () => void {
  if (!api) return () => undefined
  const createMic = deps.createMic ?? (() => new MicCapture())
  const createPlayer = deps.createPlayer ?? (() => new AudioPlayer())
  const playClip = deps.playClip ?? defaultPlayClip
  let mic: AudioInput | null = null
  let player: AudioOutput | null = null
  let clip: { stop: () => void } | null = null
  const offs: Array<() => void> = []

  const ensurePlayer = async (): Promise<AudioOutput> => {
    if (!player) {
      player = createPlayer()
      player.onIdle(() => api.playbackIdle())
    }
    await player.init()
    return player
  }

  offs.push(
    api.onMicStart(({ reqId }) => {
      void (async () => {
        try {
          mic?.stop()
          mic = createMic()
          await mic.start((b64, level) => api.micChunk(b64, level))
          api.micResult({ reqId, ok: true })
        } catch (err) {
          mic?.stop()
          mic = null
          api.micResult({ reqId, ok: false, code: isPermissionError(err) ? 'permission' : 'device' })
        }
      })()
    }),
    api.onMicStop(() => {
      mic?.stop()
      mic = null
    }),
    api.onPlay((b64) => {
      void ensurePlayer().then((p) => p.play(b64))
    }),
    api.onFlush(() => player?.flush()),
    api.onClipPlay(({ reqId, mime, bytes }) => {
      clip?.stop()
      const run = playClip(bytes, mime)
      clip = run
      void run.done.then((ok) => {
        if (clip === run) clip = null
        api.clipDone({ reqId, ok })
      })
    }),
    api.onClipStop(() => {
      clip?.stop()
      clip = null
    }),
  )

  return () => {
    for (const off of offs) off()
    mic?.stop()
    mic = null
    player?.close()
    player = null
    clip?.stop()
    clip = null
  }
}
