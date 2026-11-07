// One identity: Understudy. The old placeholder personas (Marcus, Amelia) are gone from every screen and setting; their entries stay
// below (`legacy`) only so the dormant wake and demo code and their tests keep compiling. Config only; nothing else in the codebase
// may hard-code a name.
import type { PersonaId } from './protocol'

export interface PersonaConfig {
  id: PersonaId
  displayName: string
  gender: 'male' | 'female'
  // Lower-case phrases the wake spotter listens for.
  wakePhrases: string[]
  // Common mishearings / misspellings; matched fuzzily by the spotter.
  wakeAliases: string[]
  // The voice of this identity. Understudy speaks with the ElevenLabs "River" voice; voice stays behind its feature flag until it is
  // integrated. 'TBD' (legacy entries) makes LIVE fall back to a default voice.
  voiceName: string
  styleBlurb: string
  // Design token name (resolved by src/renderer/design) for this persona's accent colour. 'accent' means the design system's own accent.
  accentToken: string
  // Kept for old saved settings and tests only; never listed, never listened for.
  legacy?: true
}

export const PERSONAS: Record<PersonaId, PersonaConfig> = {
  understudy: {
    id: 'understudy',
    displayName: 'Understudy',
    gender: 'female',
    wakePhrases: ['hey understudy', 'hi understudy', 'ok understudy', 'okay understudy'],
    wakeAliases: ['hey under study', 'hey understudies', 'hey under studied', 'hay understudy', 'a understudy', 'hey understudy.'],
    voiceName: 'River',
    styleBlurb: 'Learns how you work, then helps at the moment you need it. Calm, brief, never in the way.',
    accentToken: 'accent',
  },
  marcus: {
    id: 'marcus',
    displayName: 'Marcus',
    gender: 'male',
    wakePhrases: ['hey marcus', 'hi marcus', 'ok marcus', 'okay marcus'],
    wakeAliases: ['hey marcos', 'hey markus', 'hey marcas', 'hey marcuss', 'hey mark us', 'hey marcus.', 'a marcus', 'hay marcus', 'hey marquis'],
    voiceName: 'TBD',
    styleBlurb: 'An unhurried, step-by-step coach. Plain words, one thing at a time, happy to repeat.',
    accentToken: 'accent-marcus',
    legacy: true,
  },
  amelia: {
    id: 'amelia',
    displayName: 'Amelia',
    gender: 'female',
    wakePhrases: ['hey amelia', 'hi amelia', 'ok amelia', 'okay amelia'],
    wakeAliases: ['hey emilia', 'hey amelie', 'hey amalia', 'hey emelia', 'hey amelya', 'hey a mealia', 'hay amelia', 'hey amelea'],
    voiceName: 'TBD',
    styleBlurb: 'Calm and concise. Short sentences, gentle pace, checks in without fuss.',
    accentToken: 'accent-amelia',
    legacy: true,
  },
}

/** What the app offers and listens for: the one identity. */
export const PERSONA_LIST: PersonaConfig[] = Object.values(PERSONAS).filter((p) => !p.legacy)
/** Every entry including the legacy ones (wake matcher tests, old saved files). */
export const ALL_PERSONA_LIST: PersonaConfig[] = Object.values(PERSONAS)
export const DEFAULT_PERSONA: PersonaId = 'understudy'

/** A saved persona id from an older version becomes the one identity. */
export function currentPersona(id: PersonaId | null | undefined): PersonaId {
  return id && !PERSONAS[id].legacy ? id : DEFAULT_PERSONA
}
