// What the glance layer has used: calls in the last hour, dollars today, time of the last call. Numbers only, kept in memory.
// A restart would reset it, so the controller seeds it from the ledger when the ledger can say (see LedgerPort.usageSince).
export interface UsageEntry {
  at: number
  usd: number
}

export interface UsageSnapshot {
  lastGlanceAt: number | null
  callsLastHour: number
  usdToday: number
  callsToday: number
}

const HOUR_MS = 3_600_000

/** Local calendar day as a number (20261107). Local, because "per day" means the worker's day. */
export function dayKey(ms: number): number {
  const d = new Date(ms)
  return d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate()
}

export class UsageMeter {
  private entries: UsageEntry[] = []

  constructor(private readonly now: () => number = Date.now) {}

  record(usd: number, at: number = this.now()): void {
    this.entries.push({ at, usd: Number.isFinite(usd) && usd > 0 ? usd : 0 })
    this.prune(at)
  }

  seed(entries: readonly UsageEntry[]): void {
    for (const e of entries) if (Number.isFinite(e.at)) this.entries.push({ at: e.at, usd: Number.isFinite(e.usd) && e.usd > 0 ? e.usd : 0 })
    this.entries.sort((a, b) => a.at - b.at)
    this.prune(this.now())
  }

  snapshot(at: number = this.now()): UsageSnapshot {
    this.prune(at)
    const today = dayKey(at)
    let calls = 0
    let usd = 0
    let callsToday = 0
    let last: number | null = null
    for (const e of this.entries) {
      if (at - e.at < HOUR_MS && e.at <= at) calls++
      if (dayKey(e.at) === today) {
        usd += e.usd
        callsToday++
      }
      if (last === null || e.at > last) last = e.at
    }
    return { lastGlanceAt: last, callsLastHour: calls, usdToday: usd, callsToday }
  }

  // Entries older than the start of yesterday cannot matter to an hourly or a daily cap.
  private prune(at: number): void {
    const cutoff = at - 2 * 24 * HOUR_MS
    if (this.entries.length > 0 && this.entries[0].at < cutoff) this.entries = this.entries.filter((e) => e.at >= cutoff)
    if (this.entries.length > 5000) this.entries = this.entries.slice(-5000)
  }
}
