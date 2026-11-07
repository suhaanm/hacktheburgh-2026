// PLACEHOLDER personas: the user will rename these. Config only; nothing else in the codebase may hard-code a name.
import type { PersonaId } from './protocol'

export interface PersonaConfig {
  id: PersonaId
  displayName: string
  gender: 'male' | 'female'
  // Lower-case phrases the wake spotter listens for.
  wakePhrases: string[]
  // Common mishearings / misspellings; matched fuzzily by the spotter.
  wakeAliases: string[]
  // Google prebuilt Live voice. 'TBD' until auditioned; LIVE falls back to a default voice for 'TBD'.
  voiceName: string
  styleBlurb: string
  // Design token name (resolved by src/renderer/design) for this persona's accent colour.
  accentToken: string
}

export const PERSONAS: Record<PersonaId, PersonaConfig> = {
  marcus: {
    id: 'marcus',
    displayName: 'Marcus',
    gender: 'male',
    wakePhrases: ['hey marcus', 'hi marcus', 'ok marcus', 'okay marcus'],
    wakeAliases: ['hey marcos', 'hey markus', 'hey marcas', 'hey marcuss', 'hey mark us', 'hey marcus.', 'a marcus', 'hay marcus', 'hey marquis'],
    voiceName: 'TBD',
    styleBlurb: 'An unhurried, step-by-step coach. Plain words, one thing at a time, happy to repeat.',
    accentToken: 'accent-marcus',
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
  },
}

export const PERSONA_LIST: PersonaConfig[] = Object.values(PERSONAS)
export const DEFAULT_PERSONA: PersonaId = 'marcus'
