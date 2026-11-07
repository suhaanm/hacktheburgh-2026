import { describe, expect, it } from 'vitest'
import { pillWord } from './Pill'

describe('pillWord', () => {
  it('shows one short, honest word', () => {
    expect(pillWord('listening_for_name', false, false)).toBe('Ready')
    expect(pillWord('live', false, false)).toBe('Listening')
    expect(pillWord('live', true, false)).toBe('Muted')
  })
  it('says screen access is needed instead of implying it can see', () => {
    expect(pillWord('live', false, true)).toBe('Screen access needed')
    expect(pillWord('listening_for_name', false, true)).toBe('Ready')
  })
})
