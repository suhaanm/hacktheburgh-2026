// Live voice, assembled. `createLive` is pure assembly of injected ports (tests drive it with fakes); `electron.ts` builds the real ports.
//
//   const live = createLive({ ... })
//   live.manager.start()                      // listens to the bus 'talk' event; a no-op unless UNDERSTUDY_X_LIVE=1 and UNDERSTUDY_FLAG_VOICE=1
//   startCue(ctx, { voice: live.voice, speaker: live.speaker, workerUsedVoice: live.workerUsedVoice })    // Cue's hooks
//
// Voice is OFF by default: with the flags unset no timer is created, nothing is minted, no socket and no microphone is opened.
import type { Bus } from '../bus'
import type { CueVoice } from '../cue/voice'
import { createCueSpeaker, createCueVoice, type LineSpeaker } from './cue-hooks'
import { createLiveManager, type LiveManager, type ManagerDeps } from './manager'
import type { ClipPlayer } from './ports'
import type { LiveSettingsStore } from './settings'

export interface CreateLiveDeps extends Omit<ManagerDeps, 'bus' | 'settings'> {
  bus: Pick<Bus, 'on'>
  settings: LiveSettingsStore
  clips: ClipPlayer
  agentUrl: string
  isLoopback: (url: string) => boolean
  fetchImpl?: typeof fetch
  // The worker's own Cue voice switch (cueVoice in the main settings).
  cueVoiceOn?: () => boolean
}

export interface LiveRegistration {
  manager: LiveManager
  voice: CueVoice
  speaker: LineSpeaker
  workerUsedVoice: () => boolean
  settings: LiveSettingsStore
  dispose: () => void
}

export function createLive(d: CreateLiveDeps): LiveRegistration {
  const manager = createLiveManager(d)
  const voice = createCueVoice({ manager, cueVoiceOn: d.cueVoiceOn })
  const busy = (): boolean => {
    const p = manager.status().phase
    return p !== 'idle' && p !== 'off'
  }
  const speaker = createCueSpeaker({ env: d.env, agentUrl: d.agentUrl, isLoopback: d.isLoopback, clip: d.clips, fetchImpl: d.fetchImpl, liveBusy: busy, cueVoiceOn: d.cueVoiceOn })
  // A fixed clip never overlaps a conversation: the key going down, or a conversation opening, cuts it at once.
  const offTalk = d.bus.on('talk', (e) => {
    if (e.phase === 'press') speaker.stop()
  })
  const offStatus = manager.subscribe((s) => {
    if (s.phase !== 'idle' && s.phase !== 'off') speaker.stop()
  })
  return {
    manager,
    voice,
    speaker,
    workerUsedVoice: () => manager.workerUsedVoice(),
    settings: d.settings,
    dispose() {
      offTalk()
      offStatus()
      manager.dispose()
    },
  }
}

export { createLiveManager } from './manager'
export type { LiveManager, LiveStatus, ManagerDeps } from './manager'
export { LiveSettingsStore, LIVE_CONSENT_TEXT, LIVE_CONSENT_SHORT, liveConsentPatch } from './settings'
export { liveFlagOn, speakerFlagOn } from './flags'
