// A tiny sequential builder so chapter timings stay correct when lines change: `say` reserves the narration slot
// (a later `say` waits for the previous clip to finish), everything else happens at the cursor.
import type { Action, Beat, ScriptLine } from './types'

export class Timeline {
  private t = 0
  private audioFreeAt = 0
  readonly beats: Beat[] = []

  constructor(private readonly lines: Map<string, ScriptLine>) {}

  get now(): number {
    return this.t
  }

  // Run an action at the cursor.
  do(...actions: Action[]): this {
    for (const action of actions) this.beats.push({ at: this.t, action })
    return this
  }

  wait(ms: number): this {
    this.t += ms
    return this
  }

  // Start narration at the cursor (or when the previous clip ends). `block` also moves the cursor to the clip's end.
  say(id: string, opts: { block?: boolean } = {}): this {
    const l = this.lines.get(id)
    if (!l) throw new Error(`unknown narration line: ${id}`)
    const start = Math.max(this.t, this.audioFreeAt)
    this.t = start
    this.beats.push({ at: start, action: { type: 'say', line: id } })
    this.audioFreeAt = start + l.durationMs
    if (opts.block) this.t = this.audioFreeAt
    return this
  }

  // Moves the cursor to when the narration so far has finished.
  untilQuiet(): this {
    this.t = Math.max(this.t, this.audioFreeAt)
    return this
  }

  // Total chapter length: the last beat or clip, plus a short breath before the next chapter.
  end(tailMs = 500): number {
    return Math.max(this.t, this.audioFreeAt, ...this.beats.map((b) => b.at)) + tailMs
  }
}
