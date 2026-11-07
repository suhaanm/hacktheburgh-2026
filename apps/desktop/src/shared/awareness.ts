// What the dock's consent card shows and sends (the awareness module's own store lives in main; see src/main/awareness-card.ts).
// Plain data only: no frame, no title, no free text from the screen.

export interface AwarenessCardState {
  // False while the layer is switched off for this build (UNDERSTUDY_X_AWARENESS): the card is hidden.
  available: boolean
  consentText: string
  consentShort: string
  // The worker agreed to the CURRENT consent text.
  agreed: boolean
  enabled: boolean
  trigger: boolean
  periodic: boolean
  strict: boolean
  intervalSec: number
  dailyUsd: number
  callsToday: number
  // The last reason a look was skipped, in plain words (null when none).
  lastSkip: string | null
}

// The card's only write: agree (trigger true, with the optional extras) or withdraw (trigger false).
export interface AwarenessChoice {
  trigger: boolean
  periodic?: boolean
  strict?: boolean
}
