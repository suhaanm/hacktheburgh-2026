// Cue tokens: every number that decides how loud Cue is, in one file. Pure data (no DOM, no Node), so the main process, the card page and
// the storyboard harness all read the same values. Change the feel of Cue here, not in the components.
//
// The idea (docs/REQ7_PLAN.md section 4): help fades. A worker who needs a lot of help (level 1) gets a ring, a chip and a step number.
// One who needs a little (level 3) gets a thin ring and nothing else, until they are stuck again, and then the chip arrives. At level 4
// Cue stays silent and only answers when asked. The engine chooses the tier; these tokens decide what each tier looks like at each level.

import type { CueLevel, CueTier } from './types'

export type RingWeight = 'regular' | 'light'

export interface LevelTokens {
  // The ring while no chip is showing (a chip makes the cue "escalated", and the ring is drawn regular then).
  ringWhenQuiet: RingWeight
  // The lowest tier at which the chip appears at this level.
  chipFromTier: CueTier
  // The mono step number on the chip.
  stepPill: boolean
}

export const CUE_TOKENS = {
  // Overlay annotation ids start with this; nothing else uses the prefix, so Cue never clears another source's marks.
  idPrefix: 'cue-',

  // What each help level looks like. L3 "Nudge me": thin ring, no chip. L2 "Walk with me": ring and chip. L1 "Watch me": ring, chip and pill.
  levels: {
    1: { ringWhenQuiet: 'regular', chipFromTier: 1, stepPill: true },
    2: { ringWhenQuiet: 'regular', chipFromTier: 2, stepPill: false },
    3: { ringWhenQuiet: 'light', chipFromTier: 3, stepPill: false },
    4: { ringWhenQuiet: 'light', chipFromTier: 4, stepPill: false },
  } satisfies Record<CueLevel, LevelTokens>,
  // The level used when the engine does not say, and the floor when the worker asked for help (an answer is never withheld).
  defaultLevel: 2 as CueLevel,
  askedLevelCeiling: 2 as CueLevel,

  // The tier at which the ghost cursor demonstrates the expert's move. Also available on request ("Show me"), at any tier.
  ghostFromTier: 3 as CueTier,
  whisperTier: 4 as CueTier,

  timing: {
    // Old cue out and new cue in at the same moment: the overlay's exit (150 ms) and enter (180 ms) overlap, the panel fades the same.
    crossfadeMs: 150,
    // Anything the worker has not touched goes away after this long.
    untouchedMs: 20_000,
    // The question card and the offer are asked once; ignoring them is an answer.
    questionIgnoreMs: 12_000,
    offerIgnoreMs: 14_000,
    // A step done within this long of the cue counts as the cue being followed.
    acceptWindowMs: 10_000,
    // The silent confirmation tick.
    confirmMs: 3_500,
    // After an answer the card collapses into the chip for the chosen step and waits this long for the engine's cue for that step.
    answerWaitMs: 6_000,
    // A ring whose screen changed gets this long to be found again before it is dropped.
    regroundMs: 1_200,
    // How often main asks the engine for the current decision.
    pollMs: 1_500,
    // Voice answer: how long to listen once.
    listenMs: 6_000,
    // Never speak within this long of the worker's last key press.
    typingQuietMs: 2_000,
  },

  // Hard caps, applied again here even though the engine applies them (the model proposes, code decides).
  caps: {
    windowMs: 10 * 60_000,
    cuesPerWindow: { quiet: 2, balanced: 3, eager: 3 } as const, // eager never goes past the hard cap of 3 in 10 minutes
    questionsPerEpisode: 1,
    // Quiet only shows tiers up to this unless the worker asked.
    quietMaxTier: 2 as CueTier,
  },

  // A box the engine is not this sure of is not drawn as a ring.
  minTargetConfidence: 0.55,
  // A screen change at least this big (the capture watcher's 0..1 score) makes the ring check that its target is still there.
  screenChangeScore: 0.04,

  chip: { maxChars: 40, maxWidth: 300, gap: 14 },
  card: { width: 280, maxOptions: 4, gap: 16 },
  placement: { margin: 14 },
  // Keys while a card is up. Only registered for as long as the card is on screen.
  keys: {
    answer: ['Alt+1', 'Alt+2', 'Alt+3', 'Alt+4'] as const,
    other: 'Alt+0',
    dismiss: 'Alt+Escape',
  },
} as const

export type CueTokens = typeof CUE_TOKENS

/** The tokens that apply to a decision's level; the engine's level when present, else the default. A request for help is at least level 2. */
export function levelTokens(level: CueLevel | null, asked: boolean): LevelTokens {
  const base = level ?? CUE_TOKENS.defaultLevel
  const effective = (asked ? Math.min(base, CUE_TOKENS.askedLevelCeiling) : base) as CueLevel
  return CUE_TOKENS.levels[effective]
}
