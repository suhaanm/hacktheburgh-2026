// The awareness module seen by the shell: the dock's consent card and the tray's checkboxes. Pure adapters over `Awareness` (no Electron),
// so the rules are tested: the card is the ONE place the worker agrees to a glance (it shows CONSENT_TEXT and records its version);
// nothing else turns glances up, and turning down is always allowed.
import { z } from 'zod'
import type { Awareness } from './awareness'
import { CONSENT_SHORT, CONSENT_TEXT } from './awareness/settings'
import type { AwarenessCardState, AwarenessChoice } from '../shared/awareness'
import type { TrayAwareness } from './tray'

type AwarenessLike = Pick<Awareness, 'getAwarenessState' | 'setConsent' | 'setSwitch'>

export const AwarenessChoiceSchema = z.object({ trigger: z.boolean(), periodic: z.boolean().optional(), strict: z.boolean().optional() }).strict()

export function cardState(aw: AwarenessLike | null, flagOn: boolean): AwarenessCardState {
  if (!aw || !flagOn) return { available: false, consentText: CONSENT_TEXT, consentShort: CONSENT_SHORT, agreed: false, enabled: false, trigger: false, periodic: false, strict: true, intervalSec: 30, dailyUsd: 0, callsToday: 0, lastSkip: null }
  const s = aw.getAwarenessState()
  return {
    available: true,
    consentText: s.consentText,
    consentShort: CONSENT_SHORT,
    agreed: s.consent.recordedVersion === s.consent.currentVersion && s.consent.trigger,
    enabled: s.enabled,
    trigger: s.consent.trigger,
    periodic: s.consent.periodic,
    strict: s.strict,
    intervalSec: s.periodicIntervalSec,
    dailyUsd: s.usage.dailyUsd,
    callsToday: s.usage.callsToday,
    lastSkip: s.last.skip ? s.last.skip.reason : null,
  }
}

/** The card's write. A choice that does not parse is refused (never partly applied). Returns the new state. */
export function applyChoice(aw: AwarenessLike, raw: unknown, flagOn: boolean): AwarenessCardState {
  const parsed = AwarenessChoiceSchema.safeParse(raw)
  if (!parsed.success || !flagOn) return cardState(aw, flagOn)
  const c: AwarenessChoice = parsed.data
  aw.setConsent({ trigger: c.trigger, periodic: c.trigger && c.periodic === true, ...(c.strict !== undefined ? { strict: c.strict } : {}) })
  return cardState(aw, flagOn)
}

export function trayAwareness(aw: AwarenessLike): TrayAwareness {
  return {
    view() {
      const s = aw.getAwarenessState()
      return { enabled: s.enabled, onTrigger: s.consent.trigger, periodic: s.consent.periodic, calls: s.usage.callsToday, lastSkip: s.last.skip ? s.last.skip.reason : null }
    },
    setSwitch: (name, on) => {
      const r = aw.setSwitch(name, on)
      return { needsConsent: r.needsConsent }
    },
  }
}
