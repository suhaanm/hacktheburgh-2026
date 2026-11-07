import { describe, expect, it } from 'vitest'
import { handleCue, type CueAudio } from './showtime-cues'

function fake() {
  const log: string[] = []
  const events: Array<{ name: string; detail?: unknown }> = []
  const audio: CueAudio = {
    play: (b, m) => log.push(`play:${b}:${m}`),
    stop: () => log.push('stop'),
    pause: () => log.push('pause'),
    resume: () => log.push('resume'),
  }
  return { log, events, audio, dispatch: (name: string, detail?: unknown) => events.push({ name, detail }) }
}

describe('dock showtime cues', () => {
  it('plays a clip when one came with the line, and stays silent (captions only) when it did not', () => {
    const f = fake()
    handleCue({ type: 'say', id: 'c1-hello', text: 'Hi', persona: 'marcus', audioBase64: 'AAA', mime: 'audio/wav' }, f.audio, f.dispatch)
    handleCue({ type: 'say', id: 'c1-more', text: 'More', persona: 'marcus' }, f.audio, f.dispatch)
    expect(f.log).toEqual(['play:AAA:audio/wav'])
  })

  it('maps audio control cues', () => {
    const f = fake()
    for (const type of ['stop-audio', 'pause-audio', 'resume-audio'] as const) handleCue({ type }, f.audio, f.dispatch)
    expect(f.log).toEqual(['stop', 'pause', 'resume'])
  })

  it('turns view, chat and profile cues into the dock window events', () => {
    const f = fake()
    handleCue({ type: 'view', view: 'progress' }, f.audio, f.dispatch)
    handleCue({ type: 'chat', id: 'q1', role: 'user', text: 'Hello' }, f.audio, f.dispatch)
    handleCue({ type: 'profile-refresh' }, f.audio, f.dispatch)
    expect(f.events).toEqual([
      { name: 'alongside:showtime-view', detail: { view: 'progress' } },
      { name: 'alongside:showtime-chat', detail: { id: 'q1', role: 'user', text: 'Hello', final: true, via: 'typed' } },
      { name: 'alongside:showtime-profile', detail: undefined },
    ])
  })
})
