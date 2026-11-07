// Showtime cues in the dock window: plays the pre-rendered narration clip and turns view/chat/profile cues into the
// window events the dock's own components already listen for. Silent (captions only) when a clip is missing.
import type { ShowtimeApi, ShowtimeCue } from '../../shared/showtime'

export interface CueAudio {
  play(base64: string, mime: string): void
  stop(): void
  pause(): void
  resume(): void
}

export function createCueAudio(): CueAudio {
  let current: HTMLAudioElement | null = null
  return {
    play(base64, mime) {
      this.stop()
      const el = new Audio(`data:${mime};base64,${base64}`)
      current = el
      el.onended = () => {
        if (current === el) current = null
      }
      void el.play().catch(() => undefined)
    },
    stop() {
      if (!current) return
      current.pause()
      current = null
    },
    pause() {
      current?.pause()
    },
    resume() {
      void current?.play().catch(() => undefined)
    },
  }
}

export function handleCue(cue: ShowtimeCue, audio: CueAudio, dispatch: (name: string, detail?: unknown) => void): void {
  switch (cue.type) {
    case 'say':
      if (cue.audioBase64) audio.play(cue.audioBase64, cue.mime ?? 'audio/wav')
      return
    case 'stop-audio':
      audio.stop()
      return
    case 'pause-audio':
      audio.pause()
      return
    case 'resume-audio':
      audio.resume()
      return
    case 'view':
      dispatch('alongside:showtime-view', { view: cue.view })
      return
    case 'chat':
      dispatch('alongside:showtime-chat', { id: cue.id, role: cue.role, text: cue.text, final: true, via: 'typed' })
      return
    case 'profile-refresh':
      dispatch('alongside:showtime-profile')
      return
  }
}

export function startShowtimeCues(): () => void {
  const api = (window.alongside as unknown as { showtime?: ShowtimeApi }).showtime
  if (!api) return () => undefined
  const audio = createCueAudio()
  const off = api.onCue((cue) => handleCue(cue, audio, (name, detail) => window.dispatchEvent(new CustomEvent(name, { detail }))))
  return () => {
    off()
    audio.stop()
  }
}
