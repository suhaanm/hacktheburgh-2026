// Cost and usage for Live. PRICES ARE ASSUMPTIONS, labelled as such: the defaults are the paid-tier figures on the vendor's public pricing
// page as read on 7 Nov 2026 (the page is undated), per minute of audio and per million tokens of image and text; set the environment to
// change them. Numbers only: seconds, counts, enums and dollars. Never audio, never a transcript, never an image.
//
// Two estimates are kept and the LARGER is used for the caps, so a cap errs towards stopping early:
//   by time   audio sent and received in minutes, plus frames at an assumed token count each;
//   by tokens the server's own usageMetadata, per modality, at the per-million prices.
import fs from 'node:fs'
import path from 'node:path'
import { dayKey } from '../awareness/usage'
import type { TokenDetail, UsageReport } from './wire'

export interface LivePrices {
  audioInPerMin: number
  audioOutPerMin: number
  audioInPerM: number
  audioOutPerM: number
  imageInPerM: number
  textInPerM: number
  textOutPerM: number
  // Tokens one JPEG frame is assumed to cost (it is not reported separately by the server).
  frameTokens: number
  source: 'env' | 'assumed_default'
}

const num = (v: string | undefined): number | null => {
  if (v === undefined || v.trim() === '') return null
  const n = Number(v)
  return Number.isFinite(n) && n >= 0 ? n : null
}

export function pricesFromEnv(env: Record<string, string | undefined> = process.env): LivePrices {
  const pick = (name: string, fallback: number): { v: number; fromEnv: boolean } => {
    const n = num(env[`UNDERSTUDY_PRICE_GEMINI_LIVE_${name}`])
    return n === null ? { v: fallback, fromEnv: false } : { v: n, fromEnv: true }
  }
  const parts = {
    audioInPerMin: pick('AUDIO_IN_PER_MIN', 0.005),
    audioOutPerMin: pick('AUDIO_OUT_PER_MIN', 0.018),
    audioInPerM: pick('AUDIO_IN_PER_M', 3.0),
    audioOutPerM: pick('AUDIO_OUT_PER_M', 12.0),
    imageInPerM: pick('IMAGE_IN_PER_M', 1.0),
    textInPerM: pick('TEXT_IN_PER_M', 0.75),
    textOutPerM: pick('TEXT_OUT_PER_M', 4.5),
    frameTokens: pick('FRAME_TOKENS', 258),
  }
  const anyEnv = Object.values(parts).some((p) => p.fromEnv)
  return {
    audioInPerMin: parts.audioInPerMin.v,
    audioOutPerMin: parts.audioOutPerMin.v,
    audioInPerM: parts.audioInPerM.v,
    audioOutPerM: parts.audioOutPerM.v,
    imageInPerM: parts.imageInPerM.v,
    textInPerM: parts.textInPerM.v,
    textOutPerM: parts.textOutPerM.v,
    frameTokens: parts.frameTokens.v,
    source: anyEnv ? 'env' : 'assumed_default',
  }
}

function tokenCost(details: readonly TokenDetail[], fallbackTotal: number | null, p: LivePrices, side: 'in' | 'out'): number {
  const rate = (modality: string): number => {
    const m = modality.toUpperCase()
    if (m === 'AUDIO') return side === 'in' ? p.audioInPerM : p.audioOutPerM
    if (m === 'IMAGE' || m === 'VIDEO') return side === 'in' ? p.imageInPerM : p.textOutPerM
    return side === 'in' ? p.textInPerM : p.textOutPerM
  }
  if (details.length > 0) return details.reduce((s, d) => s + (d.tokenCount * rate(d.modality)) / 1e6, 0)
  return fallbackTotal === null ? 0 : (fallbackTotal * (side === 'in' ? p.textInPerM : p.textOutPerM)) / 1e6
}

export interface SessionCost {
  byTimeUsd: number
  byTokensUsd: number
  usd: number
}

export class SessionMeter {
  audioInSeconds = 0
  audioOutSeconds = 0
  frames = 0
  frameBytes = 0
  turns = 0
  inputTokens = 0
  outputTokens = 0
  private tokensUsd = 0
  private readonly prices: LivePrices

  constructor(prices: LivePrices = pricesFromEnv()) {
    this.prices = prices
  }

  addAudioIn(seconds: number): void {
    if (Number.isFinite(seconds) && seconds > 0) this.audioInSeconds += seconds
  }

  addAudioOut(seconds: number): void {
    if (Number.isFinite(seconds) && seconds > 0) this.audioOutSeconds += seconds
  }

  addFrames(count: number, bytes: number): void {
    this.frames += count
    this.frameBytes += bytes
  }

  /** One usageMetadata report from the server (per turn). Thought tokens are billed as output. */
  addUsage(u: UsageReport): void {
    this.turns += 1
    this.inputTokens += u.promptTokens ?? 0
    this.outputTokens += (u.responseTokens ?? 0) + (u.thoughtsTokens ?? 0)
    const out = tokenCost(u.responseDetails, u.responseTokens, this.prices, 'out') + ((u.thoughtsTokens ?? 0) * this.prices.textOutPerM) / 1e6
    this.tokensUsd += tokenCost(u.promptDetails, u.promptTokens, this.prices, 'in') + out
  }

  cost(): SessionCost {
    const p = this.prices
    const byTime =
      (this.audioInSeconds / 60) * p.audioInPerMin + (this.audioOutSeconds / 60) * p.audioOutPerMin + (this.frames * p.frameTokens * p.imageInPerM) / 1e6
    return { byTimeUsd: byTime, byTokensUsd: this.tokensUsd, usd: Math.max(byTime, this.tokensUsd) }
  }

  usd(): number {
    return this.cost().usd
  }

  priceSource(): LivePrices['source'] {
    return this.prices.source
  }

  /** The estimated cost of `count` frames, for the ledger row. */
  frameCost(count: number): number {
    return (count * this.prices.frameTokens * this.prices.imageInPerM) / 1e6
  }
}

// ------------------------------------------------------------------------------------------------ the day's total, kept across restarts
export interface UsageRow {
  t: string
  day: number
  mode: 'converse' | 'transcribe'
  seconds_in: number
  seconds_out: number
  frames: number
  turns: number
  usd: number
  ended: string
  price_source: LivePrices['source']
  model: string
}

export interface UsageLog {
  record(row: UsageRow): void
  todayUsd(now: number): number
  todaySessions(now: number): number
  rows(): readonly UsageRow[]
}

const round6 = (n: number): number => Math.round(n * 1e6) / 1e6

/** Metadata-only JSONL in the user-data directory (mode 0600). dir === null keeps it in memory (tests). */
export function createUsageLog(dir: string | null): UsageLog {
  const file = dir ? path.join(dir, 'live-usage.jsonl') : null
  let list: UsageRow[] = []
  if (file) {
    try {
      const cutoff = dayKey(Date.now() - 3 * 86_400_000)
      for (const line of fs.readFileSync(file, 'utf8').split('\n')) {
        if (!line.trim()) continue
        try {
          const r = JSON.parse(line) as UsageRow
          if (typeof r.day === 'number' && r.day >= cutoff && typeof r.usd === 'number') list.push(r)
        } catch {
          /* a half-written line is skipped */
        }
      }
    } catch {
      /* no file yet */
    }
  }
  return {
    record(row) {
      const clean: UsageRow = { ...row, usd: round6(row.usd), seconds_in: Math.round(row.seconds_in * 10) / 10, seconds_out: Math.round(row.seconds_out * 10) / 10 }
      list.push(clean)
      if (list.length > 2000) list = list.slice(-2000)
      if (!file) return
      try {
        fs.mkdirSync(path.dirname(file), { recursive: true })
        fs.appendFileSync(file, JSON.stringify(clean) + '\n', { mode: 0o600 })
      } catch {
        /* advisory: a lost line never breaks a session */
      }
    },
    todayUsd: (now) => list.filter((r) => r.day === dayKey(now)).reduce((s, r) => s + r.usd, 0),
    todaySessions: (now) => list.filter((r) => r.day === dayKey(now)).length,
    rows: () => list,
  }
}

// ------------------------------------------------------------------------------------------------ circuit breaker
export interface BreakerOptions {
  failures?: number
  windowMs?: number
  openMs?: number
  now?: () => number
}

/** Three failures within five minutes open the breaker for five minutes: the voice path steps aside and the text card carries on. */
export class CircuitBreaker {
  private fails: number[] = []
  private openedAt: number | null = null
  private readonly max: number
  private readonly windowMs: number
  private readonly openMs: number
  private readonly now: () => number

  constructor(o: BreakerOptions = {}) {
    this.max = o.failures ?? 3
    this.windowMs = o.windowMs ?? 300_000
    this.openMs = o.openMs ?? 300_000
    this.now = o.now ?? Date.now
  }

  failure(): void {
    const t = this.now()
    this.fails = this.fails.filter((x) => t - x < this.windowMs)
    this.fails.push(t)
    if (this.fails.length >= this.max) this.openedAt = t
  }

  success(): void {
    this.fails = []
    this.openedAt = null
  }

  isOpen(): boolean {
    if (this.openedAt === null) return false
    if (this.now() - this.openedAt >= this.openMs) {
      this.openedAt = null
      this.fails = []
      return false
    }
    return true
  }

  retryInMs(): number {
    return this.openedAt === null ? 0 : Math.max(0, this.openMs - (this.now() - this.openedAt))
  }
}
