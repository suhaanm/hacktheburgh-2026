// The wake phrase "hey knack", as a PURE function over one utterance's text. No audio, no I/O, no clock (the cooldown takes `now`).
//
// WHERE THIS RUNS. The real detector is the native helper (native/knack-wake/Matcher.swift), because the recognised words must never leave the
// helper: it prints only `heard`. That file is a line-for-line port of THIS one, and `scripts/wake-parity.sh` runs both over the whole corpus
// and fails if they disagree. This TypeScript copy is the specification, the unit tests' subject and the offline measurement's subject.
//
// THE RULE (a closed accept list, not a fuzzy score):
//   1. Normalise: lower case, curly apostrophes straight, everything that is not a letter, digit or apostrophe is a separator. A token remembers
//      whether a sentence or clause mark (. ? ! ; ,) sat between it and the token before it.
//   2. A GREETING token (hey, hay, heya, heyy) must start an utterance: it is the first token, or only lead-in words (oh, okay, so, um ...)
//      come before it, or it follows a sentence-ending mark (. ? ! ;). A comma alone does not start an utterance.
//   3. The very next token must be a NAME from the closed list, in one of three strengths:
//        exact  knack                         accepted at once, unless it is glued to a following word that makes it a different phrase ("knack for").
//        close  nack, nac, knak               same pronunciation, spelled the way a recogniser might: accepted at the end of the utterance, or when a
//                                             clause mark follows, or when the next word looks like the start of a request ("can", "show", "where" ...).
//        weak   knock, nock                   a real, common word: accepted only when the next word is a request starter (STRICT_FIT). Never at the end.
//   4. At the end of the text, a close or weak name may still be followed by more words, so the answer is `wait` until the caller says the
//      utterance has settled (`settled: true`: the recogniser went quiet, or its result is final). Then the end-of-utterance rules above apply.
//   5. Anything else is `reject`: "hey Jack", "hey neck", "knack" inside a sentence, "a knack for it", "hey knock it off".
//
// Nothing here ever stores or logs the text it is given.

export type WakeVerdict = 'accept' | 'wait' | 'reject'
export type WakeVariant = 'exact' | 'close' | 'weak'
export interface WakeMatch {
  verdict: WakeVerdict
  variant?: WakeVariant
}

export const GREETINGS: readonly string[] = ['hey', 'hay', 'heya', 'heyy']
export const LEAD_INS: readonly string[] = ['oh', 'ok', 'okay', 'so', 'um', 'uh', 'well', 'right', 'alright', 'and', 'but', 'now', 'hmm', 'er', 'yeah', 'yes', 'hi', 'hello']
export const NAMES_EXACT: readonly string[] = ['knack']
export const NAMES_CLOSE: readonly string[] = ['nack', 'nac', 'knak']
export const NAMES_WEAK: readonly string[] = ['knock', 'nock']
export const FIT: readonly string[] = [
  'can', 'could', 'would', 'will', 'please', 'show', 'point', 'help', 'what', 'whats', "what's", 'where', 'wheres', "where's", 'how', 'hows', "how's",
  'why', 'who', 'which', 'when', 'tell', 'find', 'guide', 'walk', 'explain', 'take', 'look', "let's", 'lets', 'i', "i'm", 'im', "i've", 'ive', "i'd", 'id',
  'my', 'me', 'do', 'does', 'did', 'is', 'are', 'you', 'ok', 'okay', 'thanks', 'thank', 'hello', 'hi', 'listen', 'stop', 'wait', 'start', 'open', 'click',
  'go', 'give', 'need', 'want', 'so', 'um', 'uh',
]
export const STRICT_FIT: readonly string[] = [
  'can', 'could', 'would', 'will', 'please', 'show', 'point', 'help', 'what', 'whats', "what's", 'where', 'wheres', "where's", 'how', 'hows', "how's",
  'why', 'which', 'tell', 'find', 'guide', 'walk', 'explain', 'i', "i'm", 'im', "i've", 'ive', "i'd", 'id', "let's", 'lets', 'ok', 'okay', 'thanks',
]
// Words that, glued straight after the name (no clause mark between), turn it into a different phrase: "a knack for", "knock it off", "knock knock".
export const BLOCK_NEXT: readonly string[] = [
  'for', 'of', 'at', 'on', 'off', 'out', 'down', 'up', 'over', 'the', 'a', 'an', 'that', 'this', 'these', 'those', 'it', 'him', 'her', 'them', 'us', 'back',
  'around', 'before', 'after', 'twice', 'once', 'three', 'times', 'knock', 'nack', 'knack', 'nock',
]
// A mark of these kinds between two words is a clause boundary; the first four also end a sentence.
const SENTENCE_MARKS = '.?!;'
const BOUNDARY_MARKS = '.?!;,'

export interface Token {
  word: string
  /** A sentence or clause mark (or the start of the text) sits before this token. */
  boundaryBefore: boolean
  /** A sentence-ending mark (or the start of the text) sits before this token: a comma does not count. */
  sentenceBefore: boolean
}

const isWordChar = (c: string): boolean => (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c === "'"

/** Lower case, straight apostrophes, tokens with their boundary flags. Pure and total: any string tokenises. */
export function tokenize(raw: string): Token[] {
  const text = String(raw).toLowerCase().replace(/[‘’ʼ`]/g, "'")
  const tokens: Token[] = []
  let cur = ''
  let boundary = true
  let sentence = true
  const flush = (): void => {
    const w = cur.replace(/^'+|'+$/g, '')
    if (w) {
      tokens.push({ word: w, boundaryBefore: tokens.length === 0 ? true : boundary, sentenceBefore: tokens.length === 0 ? true : sentence })
      boundary = false
      sentence = false
    }
    cur = ''
  }
  for (const c of text) {
    if (isWordChar(c)) cur += c
    else {
      flush()
      if (BOUNDARY_MARKS.includes(c) || c === '\n') boundary = true
      if (SENTENCE_MARKS.includes(c) || c === '\n') sentence = true
    }
  }
  flush()
  return tokens
}

const has = (list: readonly string[], w: string): boolean => list.includes(w)

/**
 * The verdict for one utterance's text. `settled` says no more words are expected (the recogniser paused, or its result is final).
 * Only the text is used; a longer transcript is searched for the phrase at every position that may start an utterance.
 */
export function matchWake(text: string, opts: { settled?: boolean } = {}): WakeMatch {
  const settled = opts.settled === true
  const t = tokenize(text)
  let waiting: WakeMatch | null = null
  for (let i = 0; i + 1 < t.length; i++) {
    if (!has(GREETINGS, t[i].word)) continue
    // The greeting starts an utterance: first, after lead-ins only, or after a sentence-ending mark.
    const startsUtterance = t[i].sentenceBefore || t.slice(0, i).every((x) => has(LEAD_INS, x.word))
    if (!startsUtterance) continue
    const name = t[i + 1].word
    const variant: WakeVariant | null = has(NAMES_EXACT, name) ? 'exact' : has(NAMES_CLOSE, name) ? 'close' : has(NAMES_WEAK, name) ? 'weak' : null
    if (!variant) continue
    const next = t[i + 2]
    switch (variant) {
      case 'exact':
        if (next && !next.boundaryBefore && has(BLOCK_NEXT, next.word)) continue
        return { verdict: 'accept', variant }
      case 'close':
        if (!next) {
          if (settled) return { verdict: 'accept', variant }
          waiting = waiting ?? { verdict: 'wait', variant }
          continue
        }
        if (next.boundaryBefore || has(FIT, next.word)) return { verdict: 'accept', variant }
        continue
      case 'weak':
        if (!next) {
          if (!settled) waiting = waiting ?? { verdict: 'wait', variant }
          continue
        }
        if (has(STRICT_FIT, next.word)) return { verdict: 'accept', variant }
        continue
    }
  }
  return waiting ?? { verdict: 'reject' }
}

// ------------------------------------------------------------------------------------------------ the cooldown
export const DEFAULT_COOLDOWN_MS = 8000

export interface WakeMatcher {
  /** Feed the latest text of the current utterance. Returns true once per accepted wake, then false for the cooldown. */
  feed(text: string, opts?: { settled?: boolean }): { accepted: boolean; reason: 'accepted' | 'cooldown' | 'wait' | 'reject'; variant?: WakeVariant }
  reset(): void
}

export function createWakeMatcher(o: { cooldownMs?: number; now?: () => number } = {}): WakeMatcher {
  const now = o.now ?? Date.now
  const cooldown = Math.max(0, o.cooldownMs ?? DEFAULT_COOLDOWN_MS)
  let lastAt = -Infinity
  return {
    feed(text, opts) {
      const m = matchWake(text, opts)
      if (m.verdict === 'reject') return { accepted: false, reason: 'reject' }
      if (m.verdict === 'wait') return { accepted: false, reason: 'wait', variant: m.variant }
      const t = now()
      if (t - lastAt < cooldown) return { accepted: false, reason: 'cooldown', variant: m.variant }
      lastAt = t
      return { accepted: true, reason: 'accepted', variant: m.variant }
    },
    reset() {
      lastAt = -Infinity
    },
  }
}
