import { describe, expect, it } from 'vitest'
import { DORMANT_LINE, dormancy, type Dormancy, type WakeInputs } from './guards'

const ok: WakeInputs = {
  flagOn: true, isMac: true, mock: false, switchedOn: true, firstRunHold: false, locked: false, asleep: false, paused: false, killed: false,
  hardQuiet: { dnd: false, screenSharing: false, onCall: false, inMeeting: false }, liveSessionActive: false, agentActing: false, away: false,
}
const with_ = (p: Partial<WakeInputs>): WakeInputs => ({ ...ok, ...p })

describe('dormancy: when the listener must not run', () => {
  it('listens when nothing says otherwise', () => {
    expect(dormancy(ok)).toBeNull()
  })
  it.each<[string, Partial<WakeInputs>, Dormancy]>([
    ['the flag is off', { flagOn: false }, 'flag_off'],
    ['not a Mac', { isMac: false }, 'not_mac'],
    ['demo mode', { mock: true }, 'mock_mode'],
    ['the worker switched it off', { switchedOn: false }, 'switched_off'],
    ['set-up has not reached the permissions step', { firstRunHold: true }, 'first_run'],
    ['the screen is locked', { locked: true }, 'locked'],
    ['the Mac is asleep', { asleep: true }, 'asleep'],
    ['Knack is paused', { paused: true }, 'paused'],
    ['everything is stopped', { killed: true }, 'killed'],
    ['a meeting', { hardQuiet: { dnd: false, screenSharing: false, onCall: false, inMeeting: true } }, 'hard_quiet'],
    ['a call', { hardQuiet: { dnd: false, screenSharing: false, onCall: true, inMeeting: false } }, 'hard_quiet'],
    ['a screen share', { hardQuiet: { dnd: false, screenSharing: true, onCall: false, inMeeting: false } }, 'hard_quiet'],
    ['quiet for an hour', { hardQuiet: { dnd: true, screenSharing: false, onCall: false, inMeeting: false } }, 'hard_quiet'],
    ['a Live conversation is open', { liveSessionActive: true }, 'live_session'],
    ['an agent is acting', { agentActing: true }, 'agent_acting'],
    ['the worker is away', { away: true }, 'worker_away'],
  ])('is dormant when %s', (_label, patch, reason) => {
    expect(dormancy(with_(patch))).toBe(reason)
  })
  it('every single condition is enough on its own, and each has a plain line', () => {
    const reasons = new Set<Dormancy>()
    for (const patch of [{ flagOn: false }, { isMac: false }, { mock: true }, { switchedOn: false }, { locked: true }, { asleep: true }, { paused: true }, { killed: true }, { liveSessionActive: true }, { agentActing: true }, { away: true }] as Partial<WakeInputs>[]) {
      const r = dormancy(with_(patch))
      expect(r).not.toBeNull()
      reasons.add(r as Dormancy)
    }
    for (const r of reasons) expect(DORMANT_LINE[r].length).toBeGreaterThan(8)
    for (const line of Object.values(DORMANT_LINE)) {
      expect(line.split(/\s+/).length).toBeLessThanOrEqual(8) // a status line, within the corner-card title budget
      expect(line).not.toMatch(/[!]|please|oops/i)
    }
  })
  it('combined conditions still say dormant (the first reason wins, none is ignored)', () => {
    expect(dormancy(with_({ locked: true, liveSessionActive: true, killed: true }))).toBe('killed')
    expect(dormancy(with_({ liveSessionActive: true, away: true }))).toBe('live_session')
  })
})
