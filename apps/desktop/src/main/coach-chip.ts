// The persistent coach chip: how much of it to show, driven by the level engine (deterministic code, not the model).
//   L1 Watch me, L2 Walk with me   full   (bars and the level name)
//   L3 Nudge me                    small  (the bars)
//   L4 On my own                   dot
//   L4 and two clean runs in a row gone   (the help has faded away)
// Help comes back the same way it left: the level engine's decay lowers the level after an absence (L4 after 14 days, L3 after
// 7, L2 after 3), so a returning worker sees the chip grow again. The engine's own `chip` (GET /coach/state) wins while it answers.
import type { OverlayController } from '../shared/contracts'
import { CHIP_FADES, HELP_LEVEL_LABELS, type ChipFade, type HelpLevel } from '../shared/protocol'

export const GONE_AFTER_CLEAN = 2

export function fadeForLevel(level: HelpLevel, streakClean: number): ChipFade {
  if (level === 4) return streakClean >= GONE_AFTER_CLEAN ? 'gone' : 'dot'
  if (level === 3) return 'small'
  return 'full'
}

export function chipFromEngine(v: unknown): ChipFade | null {
  return typeof v === 'string' && (CHIP_FADES as readonly string[]).includes(v) ? (v as ChipFade) : null
}

/** "L1".."L4" (or 1..4) from the engine's coach state. */
export function levelFromEngine(v: unknown): HelpLevel | null {
  const n = typeof v === 'number' ? v : typeof v === 'string' ? Number(/^L([1-4])$/i.exec(v.trim())?.[1]) : NaN
  return n === 1 || n === 2 || n === 3 || n === 4 ? n : null
}

export interface ChipDriverDeps {
  overlay: Pick<OverlayController, 'coach'>
  // The level engine's view of the worker right now.
  local: () => { level: HelpLevel; streakClean: number }
  killed?: () => boolean
  now?: () => number
  // The engine's hint is used while it is this fresh.
  engineFreshMs?: number
  // Re-send an unchanged chip this often so the overlay's guard never removes it.
  keepAliveMs?: number
  log?: (scope: string, ...args: unknown[]) => void
}

export interface ChipDriver {
  // The engine answered GET /coach/state (null: it did not).
  setEngineHint(hint: { fade: ChipFade | null; level: HelpLevel | null } | null): void
  // Recompute and send. Called on level changes, lesson ends and a timer.
  refresh(): ChipFade
  current(): { fade: ChipFade; level: HelpLevel } | null
}

export function createChipDriver(deps: ChipDriverDeps): ChipDriver {
  const now = deps.now ?? Date.now
  const freshMs = deps.engineFreshMs ?? 10_000
  const keepMs = deps.keepAliveMs ?? 60_000
  let hint: { fade: ChipFade | null; level: HelpLevel | null; at: number } | null = null
  let sent: { fade: ChipFade; level: HelpLevel; at: number } | null = null

  return {
    setEngineHint(h) {
      hint = h ? { ...h, at: now() } : null
    },
    refresh() {
      const local = deps.local()
      const usable = hint && now() - hint.at <= freshMs ? hint : null
      const level = usable?.level ?? local.level
      let fade: ChipFade = usable?.fade ?? fadeForLevel(level, usable?.level ? 0 : local.streakClean)
      if (deps.killed?.()) fade = 'gone' // everything is stopped: the help indicator goes too
      const t = now()
      if (!sent || sent.fade !== fade || sent.level !== level || t - sent.at >= keepMs) {
        // `gone` is sent once (to fade it out) and then left alone.
        if (!(fade === 'gone' && sent?.fade === 'gone')) deps.overlay.coach?.(fade, level, HELP_LEVEL_LABELS[level])
        sent = { fade, level, at: t }
      }
      return fade
    },
    current: () => (sent ? { fade: sent.fade, level: sent.level } : null),
  }
}
