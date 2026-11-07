import { EventEmitter } from 'node:events'
import { describe, expect, it } from 'vitest'
import { createHelperSupervisor, type ChildLike, type HelperStatus } from './helper'
import { createLineSplitter, parseHelperLine } from './helper-protocol'

describe('parseHelperLine', () => {
  it('accepts the three closed events', () => {
    expect(parseHelperLine('{"event":"ready"}')).toEqual({ ok: true, event: { event: 'ready' } })
    expect(parseHelperLine('{"event":"heard"}')).toEqual({ ok: true, event: { event: 'heard' } })
    expect(parseHelperLine('{"event":"error","code":"mic_denied"}')).toEqual({ ok: true, event: { event: 'error', code: 'mic_denied' } })
  })
  it.each([
    ['text of what was heard', '{"event":"heard","text":"hey knack show me"}', 'extra_fields'],
    ['a transcript field on ready', '{"event":"ready","transcript":"x"}', 'extra_fields'],
    ['an error without a code', '{"event":"error"}', 'extra_fields'],
    ['an error with an open-ended code', '{"event":"error","code":"the user said hello"}', 'bad_code'],
    ['an error code of the wrong type', '{"event":"error","code":5}', 'bad_code'],
    ['an unknown event', '{"event":"partial"}', 'unknown_event'],
    ['no event', '{"code":"internal"}', 'unknown_event'],
    ['an array', '["heard"]', 'not_an_object'],
    ['a string', '"heard"', 'not_an_object'],
    ['null', 'null', 'not_an_object'],
    ['plain text', 'hey knack', 'not_json'],
    ['a long line', `{"event":"heard","pad":"${'x'.repeat(400)}"}`, 'too_long'],
  ])('refuses %s', (_l, line, reason) => {
    expect(parseHelperLine(line)).toEqual({ ok: false, reason })
  })
  it('splits lines across chunks and drops an over-long line whole', () => {
    const s = createLineSplitter(50)
    expect(s.push('{"event":"re')).toEqual({ lines: [], overflow: false })
    expect(s.push('ady"}\n{"event":"heard"}\n')).toEqual({ lines: ['{"event":"ready"}', '{"event":"heard"}'], overflow: false })
    const big = s.push('x'.repeat(200) + '\n{"event":"heard"}\n')
    expect(big.overflow).toBe(true)
    expect(big.lines).toEqual(['{"event":"heard"}'])
  })
})

class FakeChild extends EventEmitter implements ChildLike {
  stdout = new EventEmitter() as unknown as ChildLike['stdout']
  killed: string[] = []
  ended = false
  stdin = { end: () => void (this.ended = true) }
  pid = 4242
  say(line: string): void {
    ;(this.stdout as unknown as EventEmitter).emit('data', Buffer.from(line + '\n'))
  }
  kill(signal?: NodeJS.Signals): boolean {
    this.killed.push(signal ?? 'SIGTERM')
    return true
  }
  exit(code: number): void {
    this.emit('exit', code, null)
  }
}

function rig(over: Partial<Parameters<typeof createHelperSupervisor>[0]> = {}) {
  const children: FakeChild[] = []
  const timers: Array<{ fn: () => void; ms: number; live: boolean }> = []
  const statuses: HelperStatus[] = []
  const heard: number[] = []
  let t = 0
  const sup = createHelperSupervisor({
    binaryPath: '/x/knack-wake',
    exists: () => true,
    spawn: () => {
      const c = new FakeChild()
      children.push(c)
      return c
    },
    onHeard: () => void heard.push(t),
    onStatus: (s) => void statuses.push(s),
    setTimer: (fn, ms) => {
      const h = { fn, ms, live: true }
      timers.push(h)
      return h
    },
    clearTimer: (h) => void ((h as { live: boolean }).live = false),
    now: () => t,
    ...over,
  })
  const fire = (): void => {
    const h = timers.find((x) => x.live && x.ms < 60_000)
    if (h) {
      h.live = false
      h.fn()
    }
  }
  return { sup, children, timers, statuses, heard, fire, tick: (ms: number) => void (t += ms) }
}

describe('the supervisor', () => {
  it('does not start without a binary: blocked with one closed reason, nothing spawned', () => {
    const r = rig({ binaryPath: null })
    r.sup.start()
    expect(r.children).toHaveLength(0)
    expect(r.sup.status()).toEqual({ state: 'blocked', code: 'binary_missing' })
    const r2 = rig({ exists: () => false })
    r2.sup.start()
    expect(r2.children).toHaveLength(0)
    expect(r2.sup.status().code).toBe('binary_missing')
  })
  it('goes starting then listening on ready, and reports a heard only while listening', () => {
    const r = rig()
    r.sup.start()
    expect(r.sup.status().state).toBe('starting')
    r.children[0].say('{"event":"heard"}') // before ready: ignored
    expect(r.heard).toHaveLength(0)
    r.children[0].say('{"event":"ready"}')
    expect(r.sup.status().state).toBe('listening')
    r.children[0].say('{"event":"heard"}')
    expect(r.heard).toHaveLength(1)
  })
  it('stops the helper on any line that is not one of ours, and never reports it as a wake', () => {
    const r = rig()
    r.sup.start()
    r.children[0].say('{"event":"ready"}')
    r.children[0].say('{"event":"heard","text":"hey knack"}')
    expect(r.heard).toHaveLength(0)
    expect(r.sup.status()).toEqual({ state: 'blocked', code: 'protocol' })
    expect(r.children[0].killed).toContain('SIGTERM')
    r.sup.start()
    expect(r.children).toHaveLength(1) // blocked stays blocked until unblock()
  })
  it('does not restart after a permission or on-device failure, and shows its code', () => {
    for (const code of ['mic_denied', 'speech_denied', 'on_device_unavailable', 'locale_unsupported', 'mic_restricted', 'speech_restricted'] as const) {
      const r = rig()
      r.sup.start()
      r.children[0].say(`{"event":"error","code":"${code}"}`)
      expect(r.sup.status()).toEqual({ state: 'blocked', code })
      r.children[0].exit(3)
      expect(r.timers.filter((t) => t.live && t.ms < 60_000)).toHaveLength(0)
      expect(r.children).toHaveLength(1)
    }
  })
  it('restarts after a transient failure with a growing pause, and resets the pause once ready', () => {
    const r = rig()
    r.sup.start()
    r.children[0].say('{"event":"error","code":"audio_engine_failed"}')
    expect(r.sup.status()).toEqual({ state: 'backoff', code: 'audio_engine_failed' })
    r.children[0].exit(4)
    expect(r.timers.at(-1)?.ms).toBe(1000)
    r.fire()
    expect(r.children).toHaveLength(2)
    r.children[1].exit(4)
    expect(r.timers.at(-1)?.ms).toBe(2000)
    r.fire()
    r.children[2].say('{"event":"ready"}')
    r.children[2].exit(4)
    expect(r.timers.at(-1)?.ms).toBe(1000)
  })
  it('gives up on a crash loop', () => {
    const r = rig({ maxCrashes: 3 })
    r.sup.start()
    for (let i = 0; i < 4; i++) {
      r.children[i].exit(4)
      r.tick(1000)
      if (i < 3) r.fire()
    }
    expect(r.sup.status()).toEqual({ state: 'blocked', code: 'crash_loop' })
  })
  it('stop() ends the child, closes its stdin, cancels a pending restart and is quiet', () => {
    const r = rig()
    r.sup.start()
    r.children[0].say('{"event":"ready"}')
    r.sup.stop()
    expect(r.children[0].ended).toBe(true)
    expect(r.children[0].killed[0]).toBe('SIGTERM')
    expect(r.sup.status().state).toBe('stopped')
    r.children[0].exit(0)
    expect(r.children).toHaveLength(1)
    // a pending restart is cancelled too
    const q = rig()
    q.sup.start()
    q.children[0].exit(4)
    q.sup.stop()
    q.fire()
    expect(q.children).toHaveLength(1)
  })
  it('a spawn that throws blocks with spawn_failed; unblock allows another try', () => {
    let boom = true
    const r = rig({
      spawn: () => {
        if (boom) throw new Error('nope')
        return new FakeChild()
      },
    })
    r.sup.start()
    expect(r.sup.status()).toEqual({ state: 'blocked', code: 'spawn_failed' })
    boom = false
    r.sup.unblock()
    r.sup.start()
    expect(r.sup.status().state).toBe('starting')
  })
  it('kills hard if the child ignores the first signal', () => {
    const r = rig()
    r.sup.start()
    r.sup.stop()
    const hard = r.timers.find((t) => t.ms === 1500)
    expect(hard).toBeDefined()
    hard?.fn()
    expect(r.children[0].killed).toEqual(['SIGTERM', 'SIGKILL'])
  })
})
