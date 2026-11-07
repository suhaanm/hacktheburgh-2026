// The coach's level, driven by the level engine (deterministic code, not the model). Nothing about it stays on the screen: when the
// level CHANGES the overlay shows a small toast for two seconds ("Help level 2: Walk with me"); the level itself lives in the menu bar
// menu and the dashboard. The persistent chip below is only drawn when the person turns on the optional 7 px dot (settings.coachDot).
//   L1 Watch me, L2 Walk with me   full   (bars and the level name)
//   L3 Nudge me                    small  (the bars)
//   L4 On my own                   dot
//   L4 and two clean runs in a row gone   (the help has faded away)
// Help comes back the same way it left: the level engine's decay lowers the level after an absence (L4 after 14 days, L3 after
// 7, L2 after 3), so a returning worker sees the chip grow again. What the engine says wins while it answers: first the coach brain's
// own decision (GET /coach/next: its level and chip are what the coach is really using, study mode included), then GET /coach/state.
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

/** The attention layer's answer to "may this two-second glance be drawn?" (attention/adapter.ts admitGlance and releaseGlance). */
export interface ChipAttention {
  admitGlance(subject: string): Promise<boolean>
  releaseGlance(): void
}

/** How long the help-level glance stays up; the voice is given back after this. */
export const CHIP_GLANCE_MS = 2_000

export interface ChipDriverDeps {
  // `coach` keeps the optional dot's fade state current; `chip` is the two-second toast when the level changes.
  overlay: Pick<OverlayController, 'coach'> & Partial<Pick<OverlayController, 'chip'>>
  // The level engine's view of the worker right now.
  local: () => { level: HelpLevel; streakClean: number }
  killed?: () => boolean
  now?: () => number
  // The engine's hint is used while it is this fresh.
  engineFreshMs?: number
  // Re-send an unchanged chip this often so the overlay's guard never removes it.
  keepAliveMs?: number
  log?: (scope: string, ...args: unknown[]) => void
  // REQ-8: when set, the two-second glance asks first and is drawn only on a yes. Absent: drawn as before. `setAttention` binds it later.
  attention?: ChipAttention | null
  setTimer?: (fn: () => void, ms: number) => unknown
}

export interface ChipDriver {
  // Late binding for the attention layer (it starts after the driver exists). null unbinds.
  setAttention(a: ChipAttention | null): void
  // The engine answered GET /coach/state (null: it did not).
  setEngineHint(hint: { fade: ChipFade | null; level: HelpLevel | null } | null): void
  // The engine answered GET /coach/next with the level and chip it is acting at (null: it did not). Wins over the state hint while fresh.
  setDecisionHint(hint: { fade: ChipFade | null; level: HelpLevel | null } | null): void
  // Recompute and send. Called on level changes, lesson ends and a timer.
  // `force` sends the chip again even if nothing changed (the overlay page just (re)loaded).
  refresh(force?: boolean): ChipFade
  current(): { fade: ChipFade; level: HelpLevel } | null
}

export function createChipDriver(deps: ChipDriverDeps): ChipDriver {
  const now = deps.now ?? Date.now
  const freshMs = deps.engineFreshMs ?? 10_000
  const keepMs = deps.keepAliveMs ?? 60_000
  let hint: { fade: ChipFade | null; level: HelpLevel | null; at: number } | null = null
  let decisionHint: { fade: ChipFade | null; level: HelpLevel | null; at: number } | null = null
  let sent: { fade: ChipFade; level: HelpLevel; at: number } | null = null
  let attention: ChipAttention | null = deps.attention ?? null
  const setT = deps.setTimer ?? ((fn: () => void, ms: number) => setTimeout(fn, ms))

  // The level-change glance. With the attention layer on it must be admitted (one voice at a time), and the voice is given back after the
  // two seconds it is shown; a refusal, a failed answer or a stop in the meantime draws nothing.
  const glance = (level: HelpLevel): void => {
    const draw = (): void => deps.overlay.chip?.(level, HELP_LEVEL_LABELS[level])
    const layer = attention
    if (!layer) return draw()
    void layer
      .admitGlance(`lv_${level}`)
      .then((ok) => {
        if (!ok) return
        if (deps.killed?.()) return layer.releaseGlance()
        draw()
        setT(() => layer.releaseGlance(), CHIP_GLANCE_MS)
      })
      .catch(() => layer.releaseGlance())
  }

  return {
    setAttention(a) {
      attention = a
    },
    setEngineHint(h) {
      hint = h ? { ...h, at: now() } : null
    },
    setDecisionHint(h) {
      decisionHint = h ? { ...h, at: now() } : null
    },
    refresh(force = false) {
      const local = deps.local()
      const fresh = (h: typeof hint) => (h && now() - h.at <= freshMs && (h.fade !== null || h.level !== null) ? h : null)
      const usable = fresh(decisionHint) ?? fresh(hint)
      const level = usable?.level ?? local.level
      let fade: ChipFade = usable?.fade ?? fadeForLevel(level, usable?.level ? 0 : local.streakClean)
      if (deps.killed?.()) fade = 'gone' // everything is stopped: the help indicator goes too
      const t = now()
      // A level change (not the first reading, not a repeat) is announced once, for two seconds.
      if (!force && sent && sent.level !== level && !deps.killed?.()) glance(level)
      if (force || !sent || sent.fade !== fade || sent.level !== level || t - sent.at >= keepMs) {
        // `gone` is sent once (to fade it out) and then left alone, unless the overlay page was just reloaded.
        if (force || !(fade === 'gone' && sent?.fade === 'gone')) deps.overlay.coach?.(fade, level, HELP_LEVEL_LABELS[level])
        sent = { fade, level, at: t }
      }
      return fade
    },
    current: () => (sent ? { fade: sent.fade, level: sent.level } : null),
  }
}
