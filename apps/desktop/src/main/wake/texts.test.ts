// The words of the voice cards: every cause the voice can fail for has its own card, every card names its cause in the title, and none says anything generic or developer-only.
import { describe, expect, it } from 'vitest'
import { INFO_CARDS, REFUSAL_LINE, infoCardFor, infoCardWith } from './texts'
import { micFixAction } from '../knack/permission-bridge'
import type { Refusal, VoiceProblem } from '../live/manager'

const PROBLEMS: VoiceProblem[] = ['mic_permission', 'mic_device', 'secure_input', 'denylisted_app', 'locked', 'gate_stale', 'ledger_unavailable', 'voice_no_key', 'voice_refused', 'voice_network', 'connection_lost']
// (no_consent and not_enabled are answered by the two consent cards, not an information card: their status line says where the card is.)
const REFUSALS: Refusal[] = ['flag_off', 'paused', 'killed', 'agent_acting', 'day_cap', 'breaker_open', 'no_model', 'model_unusable', 'no_key', 'mock_mode', 'mic_permission']

describe('every voice failure has its own card', () => {
  it('a card for each problem and each refusal that stops a conversation, with a status line for each refusal', () => {
    for (const p of PROBLEMS) expect(infoCardFor(p), p).not.toBeNull()
    for (const r of REFUSALS) {
      expect(infoCardFor(r), r).not.toBeNull()
      expect(REFUSAL_LINE[r], r).toBeTruthy()
    }
    expect(REFUSAL_LINE.no_consent).toContain('Talk with Knack card')
    expect(REFUSAL_LINE.not_enabled).toBeTruthy()
  })
  it('no two different causes share one generic sentence', () => {
    const bodies = new Map<string, string>()
    for (const [k, c] of Object.entries(INFO_CARDS)) {
      const key = `${c.title}|${c.body}`
      // The same words for the same cause under two names (no_key and voice_no_key) are fine; different causes must differ.
      const same = bodies.get(key)
      if (same) expect([same, k].sort().join('+')).toMatch(/no_key\+voice_no_key|voice_no_key\+no_key/)
      bodies.set(key, k)
    }
    expect(INFO_CARDS.no_key.title).not.toBe(INFO_CARDS.mock_mode.title)
    expect(INFO_CARDS.no_model.title).not.toBe(INFO_CARDS.no_key.title)
    expect(INFO_CARDS.model_unusable.title).not.toBe(INFO_CARDS.no_model.title)
  })
  it('stays within the card budgets, in plain words', () => {
    const words = (x: string): number => x.trim().split(/\s+/).length
    for (const [k, c] of Object.entries(INFO_CARDS)) {
      expect(words(c.title), `${k} title`).toBeLessThanOrEqual(9)
      expect(words(c.body), `${k} body`).toBeLessThanOrEqual(22)
      for (const b of c.buttons) expect(words(b.label)).toBeLessThanOrEqual(3)
      for (const s of [c.title, c.body]) expect(s, k).not.toMatch(/demo|mock|synthetic|simulated|example data|sample data|stand-in|for this build|please|oops|invalid|UNDERSTUDY_|GEMINI_/i)
    }
  })
  it('the microphone card asks first when macOS was never asked, and opens the list when it said no', () => {
    expect(infoCardWith('mic_permission', { micStatus: 'not-determined' })?.buttons[0].label).toBe('Allow')
    expect(infoCardWith('blocked_mic_denied', { micStatus: 'not-determined' })?.title).toBe('Hey Knack needs the microphone.')
    expect(infoCardWith('mic_permission', { micStatus: 'denied' })?.buttons[0].label).toBe('System Settings')
    expect(infoCardWith('mic_permission')?.buttons[0].label).toBe('System Settings')
    expect(infoCardWith('secure_input', { micStatus: 'not-determined' })).toBe(INFO_CARDS.secure_input)
    expect(micFixAction('not-determined')).toBe('ask')
    for (const s of ['denied', 'restricted', 'granted', 'unknown']) expect(micFixAction(s)).toBe('open')
  })
})
