import { NormBoxSchema } from '../../shared/protocol'
import type { Annotation, AnnotationTone, GroundResult, NormBox, ScamReport, Shot } from '../../shared/protocol'
import { AgentCancelledError, AgentTimeoutError, logAgentError } from './errors'
import { defineAgent } from './ports'
import type { AgentOutcome, ScamPorts } from './ports'
import { cleanText, findInjectionPhrases, inlineSafe, INJECTION_WHY, plainSentences, splitSentences } from './text-safety'

// Covers the multi-agent analysis (hard cap 20s in the analyst) plus grounding with retries (~8s), with headroom.
export const SCAM_TIMEOUT_MS = 60_000
export const HIGHLIGHT_TTL_MS = 25_000
export const MAX_FLAGS = 5
const MAX_MESSAGE_CHARS = 6000
const FRESH_SHOT_MS = 6000
const GROUND_CONCURRENCY = 5
const BUBBLE_MAX_CHARS = 230
const MIN_WORDS_TO_SPLIT = 5
// The advice bubble waits this long for slow groundings before it is drawn without them.
const BUBBLE_WAIT_MS = 5000

export const HUMAN_CHECK_LINE =
  'Before you do anything, ring the number on the back of your bank card, or ask Age UK or someone you trust.'

const VERDICT_LINE: Record<ScamReport['verdict'], string> = {
  likely_scam: 'This looks like a scam.',
  suspicious: 'This message has some warning signs.',
  cannot_tell: 'I cannot tell for sure about this one.',
  likely_genuine: 'I could not spot clear warning signs, but I cannot promise anything about it.',
}

const DEFAULT_ADVICE: Record<ScamReport['verdict'], string> = {
  likely_scam: 'Please do not click any links or share any details.',
  suspicious: 'Please do not click any links or share any details yet.',
  cannot_tell: 'Please do not click links or share details until you have checked.',
  likely_genuine: 'Still, do not click links or share details until you have checked.',
}

const REFUSAL_SCAM_OFF =
  'Scam Shield is switched off, so I have not looked at that message. You can turn it on in settings and ask me again.'

type Flag = ScamReport['redFlags'][number]

function toneFor(verdict: ScamReport['verdict']): AnnotationTone {
  return verdict === 'likely_scam' ? 'danger' : 'warn'
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, n))
}

/**
 * The message is DATA. Anything in it that tries to instruct an AI is reported as a red flag
 * (and never followed), and it can only make the verdict more cautious.
 */
export function applyInjectionGuard(report: ScamReport, messageText: string): ScamReport {
  const phrases = findInjectionPhrases(messageText)
  if (phrases.length === 0) return report
  const known = new Set(report.redFlags.map((f) => f.phrase.toLowerCase()))
  const added: Flag[] = phrases.filter((p) => !known.has(p.toLowerCase())).map((phrase) => ({ phrase, why: INJECTION_WHY }))
  return {
    ...report,
    verdict: report.verdict === 'likely_scam' ? 'likely_scam' : 'suspicious',
    redFlags: [...added.slice(0, 2), ...report.redFlags],
  }
}

export function sanitizeReport(report: ScamReport): ScamReport {
  const redFlags = report.redFlags
    .map((f) => ({ phrase: inlineSafe(f.phrase, 120), why: inlineSafe(f.why, 140) }))
    .filter((f) => f.phrase.length >= 3)
    .slice(0, MAX_FLAGS)
  const advice = plainSentences(report.advice.join(' '), 3, 140)
  return {
    verdict: report.verdict,
    confidence: clamp(Number.isFinite(report.confidence) ? report.confidence : 0, 0, 1),
    redFlags,
    advice: advice.length > 0 ? advice : [DEFAULT_ADVICE[report.verdict]],
    // Fixed on purpose: the human-check line must always be present and never reassuring.
    humanHelp: HUMAN_CHECK_LINE,
    models: report.models.map((m) => inlineSafe(m, 60)).slice(0, 4),
    latencyMs: report.latencyMs,
  }
}

/** At most three short plain sentences: verdict, one piece of advice, the human check. Never "safe". */
export function buildSummary(report: ScamReport): string {
  return `${VERDICT_LINE[report.verdict]} ${report.advice[0] ?? DEFAULT_ADVICE[report.verdict]} ${HUMAN_CHECK_LINE}`
}

function validBox(result: GroundResult): NormBox | undefined {
  if (!result.found || !result.box) return undefined
  const parsed = NormBoxSchema.safeParse(result.box)
  if (!parsed.success) return undefined
  const { xmin, ymin, xmax, ymax } = parsed.data
  return xmax - xmin >= 4 && ymax - ymin >= 3 ? parsed.data : undefined
}

/** Whole sentences only, so the bubble never ends mid-thought. */
function fitSentences(sentences: string[], maxChars: number): string {
  const kept: string[] = []
  for (const sentence of sentences) {
    const next = [...kept, sentence].join(' ')
    if (next.length > maxChars && kept.length > 0) break
    kept.push(sentence)
  }
  return kept.join(' ')
}

export function highlightAnnotation(agentId: string, report: ScamReport, flag: Flag, index: number, boxes: NormBox[], ttlMs = HIGHLIGHT_TTL_MS): Annotation {
  const [first, ...rest] = boxes
  if (!first) throw new Error('highlight needs at least one box')
  return { id: `${agentId}-flag-${index}`, kind: 'highlightText', tone: toneFor(report.verdict), ttlMs, boxes: [first, ...rest], note: inlineSafe(flag.why, 90) }
}

/** Sits just below the lowest highlighted phrase, or near the top when nothing could be located. */
export function adviceBubble(agentId: string, report: ScamReport, located: NormBox[], ttlMs = HIGHLIGHT_TTL_MS): Annotation {
  const lowest = located.reduce<NormBox | undefined>((acc, b) => (!acc || b.ymax > acc.ymax ? b : acc), undefined)
  const at = lowest
    ? { x: clamp((lowest.xmin + lowest.xmax) / 2, 160, 840), y: clamp(lowest.ymax + 30, 70, 930) }
    : { x: 500, y: 140 }
  const text = fitSentences([VERDICT_LINE[report.verdict], ...report.advice.slice(0, 2).flatMap((a) => splitSentences(a))], BUBBLE_MAX_CHARS)
  return { id: `${agentId}-advice`, kind: 'bubble', tone: toneFor(report.verdict), ttlMs, at, text }
}

function createLimiter(max: number): <T>(work: () => Promise<T>) => Promise<T> {
  let active = 0
  const waiting: (() => void)[] = []
  return async (work) => {
    while (active >= max) await new Promise<void>((resolve) => waiting.push(resolve))
    active += 1
    try {
      return await work()
    } finally {
      active -= 1
      waiting.shift()?.()
    }
  }
}

type Located = NormBox | 'missing' | 'error'

const WRAP_HINT = 'The text may wrap onto a second line. If it does, return one box that covers all of it.'

async function groundOnce(ports: ScamPorts, phrase: string, shot: Shot, limit: ReturnType<typeof createLimiter>, mayWrap = false): Promise<Located> {
  try {
    const result = await limit(() => ports.ground(`the text "${phrase.replace(/"/g, "'")}"`, shot, mayWrap ? WRAP_HINT : undefined))
    return validBox(result) ?? 'missing'
  } catch (err) {
    if (!(err instanceof AgentCancelledError || err instanceof AgentTimeoutError)) logAgentError('scam_check.ground', err)
    return 'error'
  }
}

/**
 * One grounding call per phrase. A phrase that wraps onto a second line is reported as "not present" by the grounder,
 * so a long miss is retried as two halves; highlightText takes several boxes for exactly this case.
 */
async function locatePhrase(ports: ScamPorts, phrase: string, shot: Shot, limit: ReturnType<typeof createLimiter>): Promise<NormBox[]> {
  const words = phrase.split(/\s+/).filter(Boolean)
  const whole = await groundOnce(ports, phrase, shot, limit, words.length >= MIN_WORDS_TO_SPLIT)
  if (typeof whole === 'object') return [whole]
  if (whole === 'error' || words.length < MIN_WORDS_TO_SPLIT) return []
  const mid = Math.ceil(words.length / 2)
  const halves = await Promise.all([words.slice(0, mid), words.slice(mid)].map((part) => groundOnce(ports, part.join(' '), shot, limit)))
  return halves.filter((h): h is NormBox => typeof h === 'object')
}

/** Resolves when `work` settles or after `ms`, whichever comes first. */
function settleWithin(work: Promise<unknown>, ms: number): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms)
    void work.finally(() => {
      clearTimeout(timer)
      resolve()
    })
  })
}

export const scamCheckAgent = defineAgent<ScamPorts>({
  kind: 'scam_check',
  timeoutMs: SCAM_TIMEOUT_MS,
  title: () => 'Checking this message',

  createPorts(deps, scope) {
    // The analyst's parallel specialists announce themselves in a burst, so stages accumulate into a short checklist.
    const stages: string[] = []
    const reportStage = (message: string): void => {
      if (!stages.includes(message)) stages.push(message)
      scope.progress(stages.slice(-3).join(' · '))
    }
    const guard = <T>(work: Promise<T>): Promise<T> =>
      work.then((value) => {
        scope.signal.throwIfAborted()
        return value
      })
    return {
      settings: () => deps.settings(),
      grabScreen: () => guard(deps.capture.grab('ground')),
      analyze: (req) => guard(deps.scam.analyze(req, { onProgress: reportStage })),
      progress: reportStage,
      // precise = flash-first grounding, required for the scam path (phrases sit inside dense text).
      ground: (target, shot, hint) => guard(deps.grounder.ground({ target, shot, precise: true, ...(hint ? { hint } : {}) })),
      announce: scope.announce,
      showHighlights: (annotations, ttlMs) => scope.highlights.show(annotations, ttlMs),
      now: scope.now,
    }
  },

  async run({ agentId, payload, ports }): Promise<AgentOutcome> {
    if (!ports.settings().scamShield) {
      return { summary: REFUSAL_SCAM_OFF, tell: `${REFUSAL_SCAM_OFF} Tell the user this plainly.` }
    }

    // Dictated text is analysed as text. Otherwise the analyst reads the screenshot itself (no separate OCR step).
    const text = payload.text ? cleanText(payload.text, MAX_MESSAGE_CHARS) : ''
    const shot = text ? undefined : await ports.grabScreen()
    const url = payload.url
    ports.progress('Checking the message…')
    const raw = await ports.analyze({ ...(text ? { text } : { shot }), ...(url ? { url } : {}) })
    const report = sanitizeReport(applyInjectionGuard(raw, text))

    // The spoken result goes out the moment the report exists; highlights follow as each phrase is located.
    const summary = buildSummary(report)
    const outcome: AgentOutcome = {
      summary,
      result: { kind: 'scam_check', report },
      tell: `${summary} The worrying parts will be marked on the screen where I can find them. Say it in two short sentences, in your own words, without reassuring them about the message.`,
    }
    ports.announce(outcome)

    // The analysis took seconds and the user may have scrolled, so ground on a fresh shot.
    const groundShot = shot && ports.now() - shot.takenAt < FRESH_SHOT_MS ? shot : await ports.grabScreen()
    const flags = report.redFlags.slice(0, MAX_FLAGS)
    const located: NormBox[][] = flags.map(() => [])
    const limit = createLimiter(GROUND_CONCURRENCY)
    const tasks = flags.map(async (flag, i) => {
      const boxes = await locatePhrase(ports, flag.phrase, groundShot, limit)
      located[i] = boxes
      if (boxes.length > 0) ports.showHighlights([highlightAnnotation(agentId, report, flag, i, boxes)], HIGHLIGHT_TTL_MS)
    })
    await settleWithin(Promise.all(tasks), BUBBLE_WAIT_MS)
    ports.showHighlights([adviceBubble(agentId, report, located.flat())], HIGHLIGHT_TTL_MS)
    await Promise.all(tasks)
    return outcome
  },
})
