// When the Hey Knack listener must NOT be running: one pure function over plain booleans, evaluated again at every change. The helper is
// stopped (the microphone released) whenever this answers a reason, and started when it answers null. Code decides; nothing here is a model.
//
// Order matters only for which reason is shown; every reason stops the listener.
export type Dormancy =
  | 'flag_off' // UNDERSTUDY_X_WAKE=0
  | 'not_mac'
  | 'mock_mode' // kept for tests only: production wiring passes false (the listener has no network and no model, so it may run whenever the switch is on)
  | 'switched_off' // the worker's "Listen for Hey Knack" switch
  | 'first_run' // set-up is on screen and the permissions step has not turned the listener on yet (so the macOS prompts come in the right order)
  | 'locked' // the screen is locked
  | 'asleep' // the Mac is asleep
  | 'paused' // "Pause for 1 hour"
  | 'killed' // Stop everything is engaged
  | 'hard_quiet' // a meeting, a call, a screen share, or the worker's quiet-for-an-hour
  | 'live_session' // a Live conversation owns the microphone
  | 'agent_acting' // an agent is working for the worker (an unattended or supervised run)
  | 'worker_away' // nobody is at the keyboard

export interface WakeInputs {
  flagOn: boolean
  isMac: boolean
  mock: boolean
  switchedOn: boolean
  /** First-run set-up is showing and the worker has not reached the step that turns listening on. */
  firstRunHold: boolean
  // True when the lock-screen event says so OR the console probe says so (the caller ORs them; an unreadable probe is false, the event is the primary signal).
  locked: boolean
  asleep: boolean
  paused: boolean
  killed: boolean
  hardQuiet: { dnd: boolean; screenSharing: boolean; onCall: boolean; inMeeting: boolean }
  liveSessionActive: boolean
  agentActing: boolean
  away: boolean
}

export function dormancy(i: WakeInputs): Dormancy | null {
  if (!i.flagOn) return 'flag_off'
  if (!i.isMac) return 'not_mac'
  if (i.mock) return 'mock_mode'
  if (!i.switchedOn) return 'switched_off'
  if (i.firstRunHold) return 'first_run'
  if (i.killed) return 'killed'
  if (i.locked) return 'locked'
  if (i.asleep) return 'asleep'
  if (i.paused) return 'paused'
  const q = i.hardQuiet
  if (q.dnd || q.screenSharing || q.onCall || q.inMeeting) return 'hard_quiet'
  if (i.liveSessionActive) return 'live_session'
  if (i.agentActing) return 'agent_acting'
  if (i.away) return 'worker_away'
  return null
}

/** The plain line for each reason (the menu bar's status row and the Settings line). Fixed words, no placeholders. */
export const DORMANT_LINE: Readonly<Record<Dormancy, string>> = {
  flag_off: 'Hey Knack is off in this build',
  not_mac: 'Hey Knack works on a Mac',
  mock_mode: 'Hey Knack is off',
  switched_off: 'Hey Knack is off',
  first_run: 'Hey Knack starts after set-up',
  locked: 'Not listening while the screen is locked',
  asleep: 'Not listening while the Mac sleeps',
  paused: 'Not listening while Knack is paused',
  killed: 'Not listening while everything is stopped',
  hard_quiet: 'Not listening during a call or meeting',
  live_session: 'Talking with you now',
  agent_acting: 'Not listening while Knack works',
  worker_away: 'Not listening while you are away',
}
