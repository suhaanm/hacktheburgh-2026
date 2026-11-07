// Pure wake-phrase matcher: no DOM, no network. Driven only by the persona wake phrases and aliases it is given,
// so renaming a persona never touches this file.

export interface WakePersona<Id extends string = string> {
  id: Id
  wakePhrases: readonly string[]
  wakeAliases: readonly string[]
}

export interface WakeMatcherOptions {
  // Minimum similarity (0-1) for a fuzzy name match. Higher = fewer false triggers, more misses. Default 0.8.
  threshold?: number
  // Words that may introduce the name. Default: hey, hay, hi, ok, okay, hello.
  prefixes?: readonly string[]
  // true (default): matching needs a prefix word. The one exception is bareNameOnFinal below.
  requirePrefix?: boolean
  // ASR sometimes drops the leading "hey" (seen in real transcripts: "Amelia." / "Amelia, how do I..."). When true
  // (default), a FINAL transcript that is exactly a configured name, or starts with it followed by a comma/stop
  // (a vocative), also fires. Interim text never does, so "Marcus Aurelius was..." cannot trigger on its first word.
  bareNameOnFinal?: boolean
  // When two personas both match fuzzily, the best must beat the runner-up by this much or nothing fires.
  ambiguityMargin?: number
  // Whole words that are never accepted as a fuzzy match (real words that merely sound like a name).
  rejectWords?: readonly string[]
}

export interface WakeMatch<Id extends string = string> {
  personaId: Id
  // 1 = an exact configured phrase/alias, lower = fuzzy.
  score: number
  exact: boolean
  // The words that were taken to be the name, as heard.
  heard: string
  // Everything after the name, normalised (what the user said in the same breath).
  trailing: string
}

export interface WakeInspection<Id extends string = string> {
  match: WakeMatch<Id> | null
  ambiguous: boolean
  candidates: WakeMatch<Id>[]
}

export interface WakeMatchContext {
  // Is this a final (not interim) transcript? Needed for bareNameOnFinal.
  final?: boolean
}

export interface WakeMatcher<Id extends string = string> {
  match(text: string, ctx?: WakeMatchContext): WakeMatch<Id> | null
  inspect(text: string, ctx?: WakeMatchContext): WakeInspection<Id>
}

export const DEFAULT_PREFIXES = ['hey', 'hay', 'hi', 'ok', 'okay', 'hello'] as const
export const DEFAULT_THRESHOLD = 0.8
const DEFAULT_MARGIN = 0.06

// Real words that sound like the placeholder names but are not addresses to the assistant. Data, not logic:
// extend it when a persona is renamed (see docs/WAKE_SPIKE.md "renaming a persona").
export const DEFAULT_REJECT_WORDS = ['mark', 'marks', 'market', 'markets', 'marketing', 'marker', 'markers', 'america', 'emily', 'emilie', 'camellia', 'camelia'] as const

interface Token {
  text: string
  // True when the original text had sentence/clause punctuation between the previous token and this one.
  breakBefore: boolean
}

const HARD_BREAK = /[,;:.!?—–()\n]/

export function normalize(text: string): string {
  return text
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/['’`]/g, '')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
}

function tokenize(text: string): Token[] {
  const out: Token[] = []
  const re = /[a-z0-9À-ɏ'’]+/gi
  let last = 0
  for (const m of text.matchAll(re)) {
    const idx = m.index ?? 0
    const between = text.slice(last, idx)
    const word = normalize(m[0])
    if (word) out.push({ text: word, breakBefore: out.length > 0 && HARD_BREAK.test(between) })
    last = idx + m[0].length
  }
  return out
}

// Optimal-string-alignment distance (Levenshtein plus adjacent transpositions).
export function editDistance(a: string, b: string): number {
  if (a === b) return 0
  if (!a.length) return b.length
  if (!b.length) return a.length
  const d: number[][] = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array<number>(b.length).fill(0)])
  for (let j = 0; j <= b.length; j++) d[0]![j] = j
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1
      d[i]![j] = Math.min(d[i - 1]![j]! + 1, d[i]![j - 1]! + 1, d[i - 1]![j - 1]! + cost)
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i]![j] = Math.min(d[i]![j]!, d[i - 2]![j - 2]! + 1)
    }
  }
  return d[a.length]![b.length]!
}

export function similarity(a: string, b: string): number {
  const max = Math.max(a.length, b.length)
  return max === 0 ? 1 : 1 - editDistance(a, b) / max
}

// Coarse English consonant skeleton: "marcus", "marcos", "markus", "marquis" all collapse to the same key.
// Deliberately lossy; the first-sound check and the raw-spelling floor below keep it from over-matching.
export function phoneticKey(word: string): string {
  let w = normalize(word).replace(/\s+/g, '')
  if (!w) return ''
  w = w
    .replace(/^(kn|gn|pn)/, 'n')
    .replace(/^wr/, 'r')
    .replace(/^wh/, 'w')
    .replace(/^x/, 's')
    .replace(/x/g, 'ks')
    .replace(/ph/g, 'f')
    .replace(/sch/g, 'sk')
    .replace(/tch/g, 'x')
    .replace(/ch/g, 'x')
    .replace(/sh/g, 'x')
    .replace(/th/g, 't')
    .replace(/ck/g, 'k')
    .replace(/gh/g, '')
    .replace(/dg/g, 'j')
    .replace(/c(?=[eiy])/g, 's')
    .replace(/[cq]/g, 'k')
  const first = /^[aeiou]/.test(w) ? 'a' : ''
  const body = w
    .replace(/[aeiouyhw]/g, '')
    .replace(/b/g, 'p')
    .replace(/d/g, 't')
    .replace(/g/g, 'k')
    .replace(/v/g, 'f')
    .replace(/z/g, 's')
    .replace(/(.)\1+/g, '$1')
  return first + body
}

interface Core {
  personaId: string
  text: string // joined without spaces, for fuzzy comparison
  tokens: string[]
  key: string
  explicit: boolean // came straight from a configured phrase/alias
}

interface Built {
  cores: Core[]
  // Aliases with no recognised prefix and several words ("a marcus"): exact match at the start of the utterance only.
  bareStarts: { personaId: string; tokens: string[] }[]
}

function buildCores(personas: readonly WakePersona[], prefixes: Set<string>): Built {
  const seen = new Map<string, Core>()
  const bareStarts: Built['bareStarts'] = []
  for (const p of personas) {
    for (const raw of [...p.wakePhrases, ...p.wakeAliases]) {
      const tokens = normalize(raw).split(' ').filter(Boolean)
      if (!tokens.length) continue
      let lead = 0
      while (lead < tokens.length - 1 && prefixes.has(tokens[lead]!)) lead++
      const core = tokens.slice(lead)
      if (lead === 0 && core.length > 1) {
        bareStarts.push({ personaId: p.id, tokens: core })
        continue
      }
      const id = `${p.id}|${core.join(' ')}`
      if (!seen.has(id)) seen.set(id, { personaId: p.id, text: core.join(''), tokens: core, key: phoneticKey(core.join('')), explicit: true })
    }
  }
  return { cores: [...seen.values()], bareStarts }
}

function scoreWord(heard: string, core: Core, threshold: number): number {
  if (heard === core.text) return 1
  const lev = similarity(heard, core.text)
  const key = phoneticKey(heard)
  // Same first sound is required for any fuzzy hit: ASR rarely changes the initial consonant of a clearly spoken name.
  if (!key || key[0] !== core.key[0]) return lev >= threshold ? lev : 0
  const phon = similarity(key, core.key) - 0.05
  // The phonetic route needs the raw spellings to be at least roughly alike, so a shared skeleton alone is not enough.
  const phonScore = lev >= 0.5 ? phon : 0
  return Math.max(lev, phonScore)
}

export function createWakeMatcher<Id extends string>(personas: readonly WakePersona<Id>[], options: WakeMatcherOptions = {}): WakeMatcher<Id> {
  const threshold = options.threshold ?? DEFAULT_THRESHOLD
  const margin = options.ambiguityMargin ?? DEFAULT_MARGIN
  const requirePrefix = options.requirePrefix ?? true
  const bareNameOnFinal = options.bareNameOnFinal ?? true
  const prefixes = new Set((options.prefixes ?? DEFAULT_PREFIXES).map((p) => normalize(p)))
  const reject = new Set((options.rejectWords ?? DEFAULT_REJECT_WORDS).map((w) => normalize(w)))
  const { cores, bareStarts } = buildCores(personas, prefixes)
  const exactWords = new Set(cores.map((c) => c.text))

  function candidatesFor(text: string, ctx: WakeMatchContext): WakeMatch<Id>[] {
    const tokens = tokenize(text)
    const best = new Map<string, WakeMatch<Id>>()
    const offer = (m: WakeMatch<Id>): void => {
      const cur = best.get(m.personaId)
      if (!cur || m.score > cur.score) best.set(m.personaId, m)
    }

    for (const b of bareStarts) {
      if (b.tokens.every((t, i) => tokens[i]?.text === t)) {
        offer({ personaId: b.personaId as Id, score: 1, exact: true, heard: b.tokens.join(' '), trailing: tokens.slice(b.tokens.length).map((t) => t.text).join(' ') })
      }
    }

    for (let i = 0; i < tokens.length; i++) {
      const hasPrefix = i > 0 && prefixes.has(tokens[i - 1]!.text)
      const bareWhole = bareNameOnFinal && ctx.final === true && i === 0
      if (!hasPrefix && requirePrefix && !bareWhole) continue
      for (const core of cores) {
        const lens = new Set([core.tokens.length])
        if (core.tokens.length > 1) lens.add(core.tokens.length - 1)
        lens.add(core.tokens.length + 1)
        for (const len of lens) {
          if (len < 1 || i + len > tokens.length) continue
          let joinable = true
          for (let k = 1; k < len; k++) if (tokens[i + k]!.breakBefore) joinable = false
          if (!joinable) continue
          const window = tokens.slice(i, i + len)
          const heard = window.map((t) => t.text).join('')
          const spaced = window.map((t) => t.text).join(' ')
          const exact = heard === core.text
          // Without a prefix only an exact name counts; fuzzy always needs "hey"-style context.
          if (!exact && (!hasPrefix || reject.has(spaced) || reject.has(heard) || exactWords.has(heard))) continue
          // A prefix-less name only counts as the whole final utterance or as a vocative opening it ("Amelia, ...").
          if (!hasPrefix && !(bareWhole && (i + len === tokens.length || tokens[i + len]!.breakBefore))) continue
          const score = scoreWord(heard, core, threshold)
          if (score < threshold && !exact) continue
          offer({
            personaId: core.personaId as Id,
            score: exact ? 1 : Math.min(score, 0.99),
            exact,
            heard: spaced,
            trailing: tokens.slice(i + len).map((t) => t.text).join(' '),
          })
        }
      }
    }
    return [...best.values()].sort((a, b) => b.score - a.score)
  }

  function inspect(text: string, ctx: WakeMatchContext = {}): WakeInspection<Id> {
    const candidates = candidatesFor(text, ctx)
    const [top, second] = candidates
    if (!top) return { match: null, ambiguous: false, candidates }
    if (second && top.score - second.score < margin) return { match: null, ambiguous: true, candidates }
    return { match: top, ambiguous: false, candidates }
  }

  return { inspect, match: (text, ctx) => inspect(text, ctx).match }
}
