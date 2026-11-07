// One process-wide flag: the kill switch is on. Anything that could act on the machine (the actuator, a new session, the
// act_for_me loop) checks it first. No electron imports here, so every module can read it and tests can set it.
let killed = false
export const isKilled = (): boolean => killed
export const setKilled = (value: boolean): void => {
  killed = value
}
