import { describe, expect, it } from 'vitest'
import { listeningLightState, listeningLightText } from './ListeningLight'

describe('listeningLightState with Screen Recording blocked', () => {
  it('never claims to see the screen while blocked', () => {
    expect(listeningLightState('live', false, true)).toBe('blind')
    expect(listeningLightText('blind', 'Marcus')).toBe('Screen access needed')
  })
  it('still says it can see the screen when allowed', () => {
    expect(listeningLightState('live', false, false)).toBe('screen')
    expect(listeningLightText('screen', 'Marcus')).toBe('I can see your screen')
  })
  it('keeps muted, asleep and wake-name states unchanged', () => {
    expect(listeningLightState('live', true, true)).toBe('muted')
    expect(listeningLightState('asleep', false, true)).toBe('off')
    expect(listeningLightState('listening_for_name', false, true)).toBe('wake')
  })
})
