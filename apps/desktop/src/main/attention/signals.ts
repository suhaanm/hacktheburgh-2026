// What the router needs to know about the worker right now, as numbers and flags. None of it is content. The awareness layer already has
// the input rhythm and presence; the worker's own quiet hotkey, a screen-share or call probe and the calendar's meeting flag come from the
// shell. A reading is stamped with when it was taken: the engine treats one older than 10 s as unknown and then holds everything except safety.
export interface AttentionSignals {
  typingBurst: boolean
  quietS: number
  deepWork: boolean
  taskInProgress: boolean
  taskMarkerS: number | null
  away: boolean
  awayS: number
  locked: boolean
  dnd: boolean
  screenSharing: boolean
  onCall: boolean
  inMeeting: boolean
  voiceSession: boolean
  dashboardFocused: boolean
}

export const CALM_SIGNALS: AttentionSignals = {
  typingBurst: false, quietS: 60, deepWork: false, taskInProgress: false, taskMarkerS: null, away: false, awayS: 0, locked: false, dnd: false,
  screenSharing: false, onCall: false, inMeeting: false, voiceSession: false, dashboardFocused: false,
}

const b = (v: boolean) => (v ? '1' : '0')
const n = (v: number) => String(Math.max(0, Math.round(v * 10) / 10))

/** The query string of `GET /attention/next` for these signals at `nowMs`. Flags and numbers only. */
export function toQuery(s: AttentionSignals, nowMs: number): string {
  const q = new URLSearchParams()
  q.set('typing_burst', b(s.typingBurst))
  q.set('quiet_s', n(s.quietS))
  q.set('deep_work', b(s.deepWork))
  q.set('task_in_progress', b(s.taskInProgress))
  if (s.taskMarkerS !== null) q.set('task_marker_s', n(s.taskMarkerS))
  q.set('away', b(s.away))
  q.set('away_s', n(s.awayS))
  q.set('locked', b(s.locked))
  q.set('dnd', b(s.dnd))
  q.set('screen_sharing', b(s.screenSharing))
  q.set('on_call', b(s.onCall))
  q.set('in_meeting', b(s.inMeeting))
  q.set('voice_session', b(s.voiceSession))
  q.set('dashboard_focused', b(s.dashboardFocused))
  q.set('local_hour', String(new Date(nowMs).getHours()))
  q.set('t', String(Math.floor(nowMs / 1000)))
  return q.toString()
}

/** The same signals as a worker-state object for the body of an admission event. */
export function toStateBody(s: AttentionSignals, nowMs: number): Record<string, boolean | number> {
  const o: Record<string, boolean | number> = {
    typing_burst: s.typingBurst, quiet_s: Math.max(0, s.quietS), deep_work: s.deepWork, task_in_progress: s.taskInProgress, away: s.away,
    away_s: Math.max(0, s.awayS), locked: s.locked, dnd: s.dnd, screen_sharing: s.screenSharing, on_call: s.onCall, in_meeting: s.inMeeting,
    voice_session: s.voiceSession, dashboard_focused: s.dashboardFocused, local_hour: new Date(nowMs).getHours(),
  }
  if (s.taskMarkerS !== null) o.task_marker_s = Math.max(0, s.taskMarkerS)
  return o
}

export interface FlowTrackerOptions {
  now?: () => number
  /** Inputs within this many ms of each other, at least `burstCount` of them in `burstWindowMs`, are a typing burst. */
  burstWindowMs?: number
  burstCount?: number
  /** A gap this long ends a run of focused work. */
  breakGapMs?: number
  /** A run this long is deep work. */
  deepWorkMs?: number
}

export interface FlowTracker {
  /** One input event (a key or a click: a timestamp is all that is needed, never which key). */
  onInput(atMs?: number): void
  snapshot(): Pick<AttentionSignals, 'typingBurst' | 'quietS' | 'deepWork'> & { runS: number }
}

/** Typing burst, quiet seconds and deep work from input timestamps alone. */
export function createFlowTracker(o: FlowTrackerOptions = {}): FlowTracker {
  const now = o.now ?? Date.now
  const win = o.burstWindowMs ?? 5_000
  const need = o.burstCount ?? 3
  const gap = o.breakGapMs ?? 120_000
  const deep = o.deepWorkMs ?? 25 * 60_000
  let recent: number[] = []
  let last: number | null = null
  let runStart: number | null = null
  return {
    onInput(at = now()) {
      if (last === null || at - last >= gap) runStart = at
      last = at
      recent.push(at)
      recent = recent.filter((t) => at - t <= win)
    },
    snapshot() {
      const t = now()
      recent = recent.filter((x) => t - x <= win)
      const quiet = last === null ? 600 : Math.max(0, (t - last) / 1000)
      const inRun = last !== null && runStart !== null && t - last < gap
      return { typingBurst: recent.length >= need && quiet < 2, quietS: quiet, deepWork: inRun && t - (runStart ?? t) >= deep, runS: inRun ? (t - (runStart ?? t)) / 1000 : 0 }
    },
  }
}
