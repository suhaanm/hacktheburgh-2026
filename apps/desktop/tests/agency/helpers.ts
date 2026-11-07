// Fakes for the agency flows: real Bus / StateStore / SettingsStore (in memory), scripted confirmations, a recording actuator.
import { mkdtempSync, readFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { Bus } from '../../src/main/bus'
import { SettingsStore } from '../../src/main/settings'
import { StateStore } from '../../src/main/state'
import type { ServiceContext } from '../../src/main/context'
import type { Actuator, ActResult } from '../../src/main/actuator'
import type { AgencyDeps } from '../../src/main/agency/common'
import type { Annotation, Shot, Verdict } from '../../src/shared/protocol'
import type { Settings } from '../../src/shared/settings'

export type Answer = 'yes' | 'no' | 'null' | (() => string | null)

export interface Env {
  deps: AgencyDeps
  ctx: ServiceContext
  bus: Bus
  settings: SettingsStore
  state: StateStore
  dir: string
  calls: string[]
  asked: Array<{ question: string; options: [string, string] }>
  shown: Annotation[][]
  cleared: Array<string[] | undefined>
  answers: Answer[]
  actResults: Map<string, ActResult>
  learned: string[]
  clock: { t: number }
  auditLines(): Array<Record<string, unknown>>
  shots: Shot[]
  verdict: { v: Verdict }
  grabs: string[]
}

export function shot(tag: string, takenAt = 0): Shot {
  return { id: tag, displayId: 1, widthPx: 100, heightPx: 100, scaleFactor: 1, jpegBase64: Buffer.from(tag).toString('base64'), takenAt, overlayHidden: true }
}

export function makeEnv(opts: { agency?: Settings['agency']; accessibility?: boolean; dryRun?: boolean; stage?: string } = {}): Env {
  const dir = mkdtempSync(path.join(os.tmpdir(), 'agency-'))
  const bus = new Bus()
  const settings = new SettingsStore(null)
  settings.patch({ agency: opts.agency ?? 'ask_each' }, { trusted: true })
  const state = new StateStore(settings.get())
  settings.onChange((next) => state.patch({ settings: next }))
  const ctx: ServiceContext = { state, bus, settings, userDataDir: dir, sendOverlay: () => undefined, sendDock: () => undefined, log: () => undefined }
  const calls: string[] = []
  const asked: Env['asked'] = []
  const shown: Annotation[][] = []
  const cleared: Env['cleared'] = []
  const answers: Answer[] = []
  const actResults = new Map<string, ActResult>()
  const learned: string[] = []
  const clock = { t: 1_000_000 }
  const shots: Shot[] = []
  const grabs: string[] = []
  const verdict = { v: { completed: true, confidence: 0.95, evidence: 'ok', uncertain: false } as Verdict }
  const dryRun = opts.dryRun ?? false
  const accessibility = opts.accessibility ?? true

  const act = (name: string, detail: string): Promise<ActResult> => {
    calls.push(`${name} ${detail}`.trim())
    const forced = actResults.get(name)
    if (forced) return Promise.resolve(forced)
    return Promise.resolve(dryRun ? { ok: true, reason: 'dry-run' } : { ok: true })
  }
  const actuator: Actuator = {
    status: () => ({ accessibility, dryRun }),
    canClick: () => dryRun || accessibility,
    openUrl: (u) => act('openUrl', u),
    openApp: (n) => act('openApp', n),
    revealPath: (p) => act('revealPath', p),
    openSettingsPane: (p) => act('openSettingsPane', p),
    clickAt: (p, o) => act(o?.double ? 'doubleClick' : 'click', `${Math.round(p.x)},${Math.round(p.y)}`),
    typeText: (t) => act('type', t),
    pressKeys: (k) => act('keys', k),
    scroll: (p, dy) => act('scroll', `${Math.round(p.x)},${Math.round(p.y)},${dy}`),
  }
  let shotN = 0
  const deps: AgencyDeps = {
    ctx,
    s: {
      capture: {
        grab: async (purpose) => {
          grabs.push(purpose)
          return shots.shift() ?? shot(`auto-${purpose}-${++shotN}`, clock.t)
        },
        liveFrame: async () => ({ jpegBase64: '', changeScore: 0 }),
        watch: () => () => undefined,
      },
      overlay: {
        show: (a) => void shown.push(a),
        clear: (ids) => void cleared.push(ids),
        caption: () => undefined,
        chip: () => undefined,
      },
      verifier: { verify: async () => verdict.v },
      learner: { recordDoneForMe: async (k: string) => void learned.push(k) } as unknown as AgencyDeps['s']['learner'],
    },
    confirm: {
      ask: async (question, options) => {
        asked.push({ question, options })
        const a = answers.shift() ?? 'yes'
        if (typeof a === 'function') return a()
        return a === 'yes' ? options[0] : a === 'no' ? options[1] : null
      },
    },
    actuator,
    now: () => clock.t,
    sleep: async (ms) => void (clock.t += ms),
    stageOrigin: opts.stage ?? 'http://127.0.0.1:5180',
    homeDir: '/Users/lily',
  }
  const auditLines = (): Array<Record<string, unknown>> => {
    try {
      return readFileSync(path.join(dir, 'actions.log'), 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l) as Record<string, unknown>)
    } catch {
      return []
    }
  }
  return { deps, ctx, bus, settings, state, dir, calls, asked, shown, cleared, answers, actResults, learned, clock, auditLines, shots, verdict, grabs }
}
