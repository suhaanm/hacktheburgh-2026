import { describe, expect, it } from 'vitest'
import type { PermissionStatus } from '../../shared/permissions'
import type { HelperStatus } from '../wake/helper'
import { PERM_KINDS, paneOf, permKindOf, permissionsView, speechStateOf } from './permission-bridge'

const status = (over: Partial<PermissionStatus> = {}): PermissionStatus => ({ microphone: 'not-determined', screen: 'not-determined', accessibility: false, probe: 'skipped', needsRestart: false, hint: 'You started this from "Terminal"', ...over })
const helper = (state: HelperStatus['state'], code: HelperStatus['code'] = null): HelperStatus => ({ state, code })

describe('the kinds the page may name', () => {
  it('are exactly microphone, speech, screen and accessibility', () => {
    expect([...PERM_KINDS]).toEqual(['microphone', 'speech', 'screen', 'accessibility'])
    for (const k of PERM_KINDS) expect(permKindOf(k)).toBe(k)
  })
  it('refuse anything else before anything is asked', () => {
    for (const bad of ['camera', 'Microphone', '', 'screen ', 7, null, undefined, {}, ['screen'], '../etc']) expect(permKindOf(bad)).toBeNull()
  })
  it('each opens its own System Settings pane', () => {
    expect(PERM_KINDS.map(paneOf)).toEqual(['microphone', 'speech', 'screen', 'accessibility'])
  })
})

describe('the state the page sees', () => {
  it('nothing asked yet: every kind is not_asked and no restart is needed', () => {
    expect(permissionsView(status(), null)).toEqual({ microphone: 'not_asked', speech: 'not_asked', screen: 'not_asked', accessibility: 'not_asked', needsRestart: false })
  })
  it('maps granted, denied and restricted, and the unknown state to not_asked', () => {
    const v = permissionsView(status({ microphone: 'granted', screen: 'denied', accessibility: true }), null)
    expect(v).toMatchObject({ microphone: 'granted', screen: 'denied', accessibility: 'granted' })
    expect(permissionsView(status({ microphone: 'restricted', screen: 'unknown' }), null)).toMatchObject({ microphone: 'restricted', screen: 'not_asked' })
  })
  it('says a restart is needed only when macOS says screen recording is allowed but capture returns nothing', () => {
    expect(permissionsView(status({ screen: 'unknown', needsRestart: true }), null).needsRestart).toBe(true)
  })
  it('never carries the system hint, a path or an app name: only the five closed values', () => {
    const v = permissionsView(status({ hint: '/Applications/Terminal.app' }), helper('stopped'))
    expect(Object.keys(v).sort()).toEqual(['accessibility', 'microphone', 'needsRestart', 'screen', 'speech'])
    expect(JSON.stringify(v)).not.toMatch(/Terminal|Applications|hint/)
  })
})

describe('speech recognition, which only the Hey Knack listener can tell', () => {
  it('listening means it was allowed; a refusal is named; everything else is not asked yet', () => {
    expect(speechStateOf(helper('listening'))).toBe('granted')
    expect(speechStateOf(helper('blocked', 'speech_denied'))).toBe('denied')
    expect(speechStateOf(helper('blocked', 'speech_restricted'))).toBe('restricted')
    expect(speechStateOf(helper('blocked', 'mic_denied'))).toBe('not_asked') // that one is the microphone's
    expect(speechStateOf(helper('starting'))).toBe('not_asked')
    expect(speechStateOf(helper('stopped'))).toBe('not_asked')
    expect(speechStateOf(null)).toBe('not_asked')
  })
})
