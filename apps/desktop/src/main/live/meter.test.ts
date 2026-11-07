import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { CircuitBreaker, SessionMeter, createUsageLog, pricesFromEnv } from './meter'

const usage = (o: Partial<Parameters<SessionMeter['addUsage']>[0]> = {}) => ({ promptTokens: 564, responseTokens: 24, totalTokens: 588, thoughtsTokens: 54, promptDetails: [{ modality: 'TEXT', tokenCount: 317 }, { modality: 'AUDIO', tokenCount: 222 }], responseDetails: [{ modality: 'AUDIO', tokenCount: 24 }], ...o })

describe('prices', () => {
  it('default to the labelled assumption and say when the environment changed them', () => {
    expect(pricesFromEnv({})).toMatchObject({ audioInPerMin: 0.005, audioOutPerMin: 0.018, imageInPerM: 1.0, source: 'assumed_default' })
    const p = pricesFromEnv({ UNDERSTUDY_PRICE_GEMINI_LIVE_AUDIO_IN_PER_MIN: '0.01', UNDERSTUDY_PRICE_GEMINI_LIVE_TEXT_IN_PER_M: 'junk' })
    expect(p.audioInPerMin).toBe(0.01)
    expect(p.textInPerM).toBe(0.75)
    expect(p.source).toBe('env')
  })
})

describe('the session meter', () => {
  it('estimates by time and by tokens and uses the larger one for the caps', () => {
    const m = new SessionMeter(pricesFromEnv({}))
    m.addAudioIn(60)
    m.addAudioOut(30)
    expect(m.cost().byTimeUsd).toBeCloseTo(0.005 + 0.009, 6)
    expect(m.usd()).toBeCloseTo(0.014, 6)
    m.addUsage(usage())
    const c = m.cost()
    expect(c.byTokensUsd).toBeGreaterThan(0)
    expect(c.usd).toBe(Math.max(c.byTimeUsd, c.byTokensUsd))
    expect(m.turns).toBe(1)
    expect(m.inputTokens).toBe(564)
    expect(m.outputTokens).toBe(24 + 54)
  })
  it('bills thought tokens as output and per-modality tokens at their own prices', () => {
    const p = pricesFromEnv({})
    const m = new SessionMeter(p)
    m.addUsage({ promptTokens: 1_000_000, responseTokens: 0, totalTokens: 1_000_000, thoughtsTokens: 1_000_000, promptDetails: [{ modality: 'AUDIO', tokenCount: 1_000_000 }], responseDetails: [] })
    expect(m.cost().byTokensUsd).toBeCloseTo(p.audioInPerM + p.textOutPerM, 6)
  })
  it('counts frames at an assumed token price and ignores nonsense inputs', () => {
    const m = new SessionMeter(pricesFromEnv({}))
    m.addFrames(10, 5000)
    expect(m.frames).toBe(10)
    expect(m.cost().byTimeUsd).toBeCloseTo((10 * 258 * 1.0) / 1e6, 9)
    expect(m.frameCost(2)).toBeCloseTo((2 * 258) / 1e6, 9)
    m.addAudioIn(Number.NaN)
    m.addAudioIn(-5)
    expect(m.audioInSeconds).toBe(0)
  })
})

describe('the usage log', () => {
  const row = (o = {}) => ({ t: new Date().toISOString(), day: 0, mode: 'converse' as const, seconds_in: 12.34, seconds_out: 5, frames: 2, turns: 1, usd: 0.0123456789, ended: 'release_grace', price_source: 'assumed_default' as const, model: 'm', ...o })
  it('adds up the day and survives a restart; a day is the local day', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'live-use-'))
    const now = Date.now()
    const day = Number(`${new Date(now).getFullYear()}${String(new Date(now).getMonth() + 1).padStart(2, '0')}${String(new Date(now).getDate()).padStart(2, '0')}`)
    const log = createUsageLog(dir)
    log.record(row({ day, usd: 0.1 }))
    log.record(row({ day, usd: 0.05 }))
    log.record(row({ day: day - 1, usd: 9 }))
    expect(log.todayUsd(now)).toBeCloseTo(0.15, 6)
    expect(log.todaySessions(now)).toBe(2)
    expect(createUsageLog(dir).todayUsd(now)).toBeCloseTo(0.15, 6)
  })
  it('writes numbers, counts and enums only (0600), never text, audio or ids', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'live-use-'))
    const log = createUsageLog(dir)
    log.record(row({ day: 20261107 }))
    const file = path.join(dir, 'live-usage.jsonl')
    expect(fs.statSync(file).mode & 0o777).toBe(0o600)
    const saved = JSON.parse(fs.readFileSync(file, 'utf8').trim())
    expect(Object.keys(saved).sort()).toEqual(['day', 'ended', 'frames', 'mode', 'model', 'price_source', 'seconds_in', 'seconds_out', 't', 'turns', 'usd'])
    expect(saved.usd).toBe(0.012346)
    expect(saved.seconds_in).toBe(12.3)
  })
  it('skips a half-written line and works in memory when there is no directory', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'live-use-'))
    fs.writeFileSync(path.join(dir, 'live-usage.jsonl'), '{"day":')
    expect(createUsageLog(dir).rows()).toEqual([])
    const mem = createUsageLog(null)
    mem.record(row())
    expect(mem.rows()).toHaveLength(1)
  })
})

describe('the circuit breaker', () => {
  it('opens after three failures in five minutes, closes after five more, and a success resets it', () => {
    let t = 0
    const b = new CircuitBreaker({ now: () => t })
    b.failure()
    b.failure()
    expect(b.isOpen()).toBe(false)
    b.success()
    b.failure()
    b.failure()
    expect(b.isOpen()).toBe(false)
    b.failure()
    expect(b.isOpen()).toBe(true)
    expect(b.retryInMs()).toBe(300_000)
    t = 299_000
    expect(b.isOpen()).toBe(true)
    t = 301_000
    expect(b.isOpen()).toBe(false)
  })
  it('failures older than the window do not count', () => {
    let t = 0
    const b = new CircuitBreaker({ now: () => t })
    b.failure()
    b.failure()
    t = 400_000
    b.failure()
    expect(b.isOpen()).toBe(false)
  })
})
