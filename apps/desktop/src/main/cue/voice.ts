// Voice hooks. Cue is visual by default; these two interfaces are where the LIVE and voice tracks plug in later, and both default to nothing:
//   CueVoice.listenOnce(options)  hear one spoken answer to the question card ("the second one", "number two", the label itself).
//   CueSpeaker.say(lineId)        speak one cached pack line (a whisper, tier 4), at most eight words.
// The defaults never open the microphone and never speak. Cue's controller only calls them when the worker turned cueVoice on, the build
// allows voice (UNDERSTUDY_VOICE=1) and the guards in guards.ts say it is a good moment.

export interface VoiceOption {
  id: string
  label: string
}

export interface CueVoice {
  /** Listens once and resolves with the chosen option's id, OTHER_OPTION_ID for "something else", or null (silence, no match, or ambiguous). */
  listenOnce(options: readonly VoiceOption[], opts?: { timeoutMs?: number }): Promise<string | null>
}

export interface CueSpeaker {
  /** Speaks a cached line by id. Resolves when it has finished (or immediately if it did not speak). */
  say(lineId: string): Promise<void> | void
  stop?(): void
  /** Cue tells the speaker which words an id stands for (the engine's whisper_id and whisper text) just before it calls say(id). */
  registerLine?(id: string, text: string): void
}

/**
 * What the voice tools (the LIVE track's point_at, show_step, ask_choice) may do through Cue. The model can only name ids from `candidates()`.
 * Implemented by Cue (live-port.ts); LIVE calls it.
 */
export interface LiveCuePort {
  /** The closed list of pack steps for the current situation, at most 6. */
  candidates(): Array<{ id: string; label: string }>
  /** Shows the step as a chip (and its ring when the engine gave a box). `chip` is the words shown, or null when nothing could be shown. */
  showStep(stepId: string): { ok: boolean; chip: string | null }
  /** Opens the question card for 2 to 4 candidate ids. False when it could not (fewer than 2 known ids, or Cue is off). */
  askChoice(optionIds: string[]): boolean
  /** The card was answered, by click, key or voice. Returns the unsubscribe. */
  onAnswer(cb: (answerId: string) => void): () => void
}

// The engine's fixed id for "something else" in a question (CUE-ENGINE `OTHER`).
export const OTHER_OPTION_ID = 'other'

/** The default voice: deaf. The microphone is never opened by Cue itself. */
export const nullVoice: CueVoice = { listenOnce: async () => null }
/** The default speaker: silent. */
export const nullSpeaker: CueSpeaker = { say: () => undefined, stop: () => undefined }

const ORDINALS: Record<string, number> = { first: 1, '1st': 1, one: 1, '1': 1, second: 2, '2nd': 2, two: 2, '2': 2, third: 3, '3rd': 3, three: 3, '3': 3, fourth: 4, '4th': 4, four: 4, '4': 4, last: -1 }
const FILLER = new Set(['the', 'a', 'an', 'one', 'number', 'option', 'choice', 'please', 'i', 'think', 'it', 'is', 'its', "it's", 'that', 'this', 'go', 'with', 'pick', 'choose', 'take', 'want', 'say', 'um', 'uh', 'er', 'then', 'step', 'to', 'of'])
const OTHER_WORDS = ['something else', 'something different', 'none of those', 'none of them', 'other', 'neither']
const norm = (s: string): string => s.toLowerCase().replace(/[^a-z0-9' ]+/g, ' ').replace(/\s+/g, ' ').trim()
const content = (s: string): string[] => norm(s).split(' ').filter((w) => w && !FILLER.has(w))

/**
 * Pure matcher for a spoken answer: "the second one", "number two", "2", "last one", the option's own words, or "something else".
 * Returns the option id, OTHER_OPTION_ID, or null when nothing matches or two options match equally well (never a guess).
 */
export function matchSpokenOption(transcript: string, options: readonly VoiceOption[]): string | null {
  const said = norm(transcript)
  if (said === '' || options.length === 0) return null
  if (OTHER_WORDS.some((w) => said.includes(w))) return OTHER_OPTION_ID

  // Ordinals and digits: only when the whole answer is little more than the ordinal ("the second one", "number 2", "two").
  const words = said.split(' ')
  const rest = words.filter((w) => !(w in ORDINALS) && !FILLER.has(w))
  let ords = words.filter((w) => w in ORDINALS)
  // "the second one": the trailing "one" is filler once a real ordinal is there.
  if (ords.length > 1) ords = ords.filter((w) => w !== 'one')
  if (ords.length === 1 && rest.length === 0) {
    const n = ORDINALS[ords[0]]
    const index = n === -1 ? options.length - 1 : n - 1
    return options[index]?.id ?? null
  }

  // Words of the option itself: the option whose content words the answer covers best, if it is clearly the best.
  const spoken = new Set(content(said))
  if (spoken.size === 0) return null
  let best: { id: string; score: number } | null = null
  let tie = false
  for (const opt of options) {
    const ow = content(opt.label)
    if (ow.length === 0) continue
    const hits = ow.filter((w) => spoken.has(w)).length
    const score = hits / ow.length
    if (hits === 0) continue
    if (!best || score > best.score + 1e-9) {
      best = { id: opt.id, score }
      tie = false
    } else if (Math.abs(score - best.score) < 1e-9) tie = true
  }
  if (!best || tie || best.score < 0.5) return null
  return best.id
}

/** A scripted voice for tests and the storyboard: each call hears the next transcript (null = silence) and matches it. */
export function createFakeVoice(transcripts: Array<string | null>): CueVoice & { calls: number } {
  let i = 0
  const voice = {
    calls: 0,
    async listenOnce(options: readonly VoiceOption[]): Promise<string | null> {
      voice.calls += 1
      const said = transcripts[i++] ?? null
      return said === null ? null : matchSpokenOption(said, options)
    },
  }
  return voice
}

/** A speaker that records what it was asked to say (tests, storyboard). */
export function createFakeSpeaker(): CueSpeaker & { said: string[] } {
  const said: string[] = []
  return { said, say: (id) => void said.push(id), stop: () => undefined }
}
