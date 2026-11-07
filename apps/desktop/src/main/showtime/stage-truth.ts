// Stage truth (interactive demo only, ALONGSIDE_DEMO_DIRECTOR=1): on the practice desktop the page itself knows where
// every control is and what state it is in, so grounding and step verification for the known lessons read that
// instead of asking a model. Anything unknown, hidden, or any failure falls through to the real grounder / verifier.
import type { Grounder, Services, Verifier, VerifyRequest } from '../../shared/contracts'
import type { GroundResult, LessonStep, NormBox, Verdict } from '../../shared/protocol'
import { FALLBACK_GROUND_IDS, fallbackPlan } from '../teaching/skills/plans'

// ---------------------------------------------------------------- the page, as seen from main
export interface StageEventLite {
  seq: number
  t: number
  type: string
  id?: string | null
}
export interface StageStateLite {
  app: string | null
  running?: string[]
  video?: { view?: string; selected?: string | null; callState?: string }
  settings?: { section?: string }
  textStep?: number
}
export interface StageTruthSource {
  // False when the practice desktop is not on screen (closed, hidden): everything then goes to the real services.
  available(): boolean
  // window.__stage.rects({space:'screen'}): visible, unoccluded ground ids -> boxes normalised 0-1000 of the display.
  rects(): Promise<Record<string, NormBox>>
  snapshot(): Promise<{ state: StageStateLite; events: StageEventLite[] }>
}

let source: StageTruthSource | null = null
export const setStageTruthSource = (s: StageTruthSource | null): void => {
  source = s
}
export const getStageTruthSource = (): StageTruthSource | null => source
export const stageTruthEnabled = (env: NodeJS.ProcessEnv = process.env): boolean => env.ALONGSIDE_DEMO_DIRECTOR === '1'

// ---------------------------------------------------------------- target resolution
const norm = (s: string): string => s.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()

const LABELS: Record<string, string> = {
  'desk.icon.video': 'VideoChat',
  'desk.icon.messages': 'Messages',
  'desk.icon.settings': 'Settings',
  'desk.icon.web': 'Web',
  'desk.icon.files': 'Files',
  'desk.icon.photos': 'Photos',
  'desk.icon.notes': 'Notes',
  'desk.icon.calendar': 'Calendar',
  'desk.icon.bin': 'Bin',
  'video.contact.lily': 'Lily',
  'video.start_call': 'Start call',
  'video.precall.join': 'Join',
  'video.call.hangup': 'Leave',
  'messages.conv.scam': 'Aldermoor Bank',
  'messages.thread.menu': 'Menu',
  'messages.thread.report': 'Report junk',
  'settings.nav.display': 'Display',
  'settings.text_larger': 'Larger',
}

let descriptionIds: Map<string, string> | null = null
function knownDescriptions(): Map<string, string> {
  if (descriptionIds) return descriptionIds
  const m = new Map<string, string>()
  for (const skill of ['video_call', 'spot_scam', 'bigger_text'] as const) {
    for (const step of fallbackPlan(skill).steps) {
      const id = FALLBACK_GROUND_IDS[step.id]
      if (id) {
        m.set(norm(step.targetDescription), id)
        m.set(norm(step.id), id)
      }
    }
  }
  descriptionIds = m
  return m
}

const ICONS: Array<[string, RegExp]> = [
  ['desk.icon.web', /^(the )?(web|browser|internet)( app| icon)?$/],
  ['desk.icon.files', /^(the )?files?( app| icon)?$/],
  ['desk.icon.photos', /^(the )?photos?( app| icon)?$/],
  ['desk.icon.notes', /^(the )?notes?( app| icon)?$/],
  ['desk.icon.calendar', /^(the )?calendar( app| icon)?$/],
  ['desk.icon.bin', /^(the )?(bin|trash|rubbish bin)( app| icon)?$/],
]

// Wording-robust rules for descriptions the exact table does not know (an architect plan, a point_at phrase).
// Ordered most specific first; a rule only fires for the wording it is sure of.
function ruleMatch(t: string): string | null {
  if (!t) return null
  const words = t.split(' ').length
  if (/\bjoin\b/.test(t) && !/toolbar|small|top bar|not the|decoy/.test(t)) return 'video.precall.join'
  if (/\b(leave|hang ?up)\b|end (the |your )?call/.test(t)) return 'video.call.hangup'
  if (/start call|start the call/.test(t)) return 'video.start_call'
  if (/\blily\b/.test(t) && /row|contact|list|name|granddaughter/.test(t) && !/button|join/.test(t)) return 'video.contact.lily'
  if (/(video ?chat|video camera|camera|video( call)? app)/.test(t) && /icon|app\b|desktop|left|column|program/.test(t) && !/contact|lily|row|button|join|window/.test(t)) return 'desk.icon.video'
  if (/\b(messages?|texts?)\b/.test(t) && /icon|app\b|desktop|left|column|speech bubble|where/.test(t) && !/conversation|aldermoor|row|menu|dots|junk|from|bank|read|link/.test(t)) return 'desk.icon.messages'
  if (/\bsettings?\b|\bgear\b/.test(t) && /icon|app\b|desktop|left|column|where/.test(t) && !/window|list|display|panel|nav|videochat|toolbar|card|slider/.test(t)) return 'desk.icon.settings'
  if (/\bdisplay\b/.test(t) && /list|left|item|nav|menu/.test(t) && !/icon/.test(t)) return 'settings.nav.display'
  if (/\b(larger|bigger)\b/.test(t) && /button/.test(t) && words < 30) return 'settings.text_larger'
  for (const [id, re] of ICONS) if (re.test(t)) return id
  return null
}

// The practice-desktop id a target description (or a step id, or a data-ground-id) stands for; null when unknown.
export function resolveTargetId(target: string): string | null {
  const t = norm(target)
  if (!t) return null
  const exact = knownDescriptions().get(t)
  if (exact) return exact
  if (LABELS[target.trim()]) return target.trim()
  return ruleMatch(t)
}

const area = (b: NormBox): number => Math.max(0, b.xmax - b.xmin) * Math.max(0, b.ymax - b.ymin)
const inScreen = (b: NormBox): boolean => b.xmin >= 0 && b.ymin >= 0 && b.xmax <= 1000 && b.ymax <= 1000 && area(b) > 0

// ---------------------------------------------------------------- grounder
export interface StageTruthOpts {
  now?: () => number
  sleep?: (ms: number) => Promise<void>
  // How long to wait for an element that is about to appear (the page is mid-transition) before asking the model.
  appearWaitMs?: number
  log?: (msg: string) => void
}
const realSleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

export function createStageTruthGrounder(real: Grounder, getSource: () => StageTruthSource | null, opts: StageTruthOpts = {}): Grounder {
  const now = opts.now ?? Date.now
  const sleep = opts.sleep ?? realSleep
  const appearWaitMs = opts.appearWaitMs ?? 450
  const log = opts.log ?? ((): void => undefined)

  async function resolveBox(target: string): Promise<{ id: string; box: NormBox } | null> {
    const src = getSource()
    if (!src || !src.available()) return null
    const id = resolveTargetId(target)
    if (!id) return null
    const deadline = now() + appearWaitMs
    for (;;) {
      const box = (await src.rects())[id]
      if (box && inScreen(box)) return { id, box: { xmin: box.xmin, ymin: box.ymin, xmax: box.xmax, ymax: box.ymax } }
      if (now() >= deadline) return null
      await sleep(60)
    }
  }

  return {
    async ground(req) {
      const started = now()
      try {
        const hit = await resolveBox(req.target)
        if (hit) {
          const res: GroundResult = {
            found: true,
            box: hit.box,
            point: { x: (hit.box.xmin + hit.box.xmax) / 2, y: (hit.box.ymin + hit.box.ymax) / 2 },
            confidence: 1,
            label: LABELS[hit.id] ?? hit.id,
            latencyMs: now() - started,
            model: 'stage-truth',
          }
          log(`ground ${hit.id} in ${res.latencyMs} ms`)
          return res
        }
      } catch (err) {
        log(`ground fell back to the real grounder: ${err instanceof Error ? err.message : String(err)}`)
      }
      return real.ground(req)
    },
    prefetch(req) {
      // A known, visible target needs no warm-up (ground() is instant); everything else warms the real grounder as before.
      void (async () => {
        try {
          const src = getSource()
          const id = src?.available() ? resolveTargetId(req.target) : null
          if (id && (await src!.rects())[id]) return
        } catch {
          // fall through to the real prefetch
        }
        real.prefetch?.(req)
      })()
    },
    invalidate() {
      real.invalidate?.()
    },
  }
}

// ---------------------------------------------------------------- verifier
type Flow = 'video_call' | 'bigger_text'
interface FlowStep {
  flow: Flow
  n: number
}

// Target id of each step, in order. Progress is read from the page state, so a learner who skips ahead still passes.
const FLOW_TARGETS: Record<Flow, string[]> = {
  video_call: ['desk.icon.video', 'video.contact.lily', 'video.start_call', 'video.precall.join', 'video.call.hangup'],
  bigger_text: ['desk.icon.settings', 'settings.nav.display', 'settings.text_larger'],
}

function progress(flow: Flow, st: StageStateLite): { n: number; seen: string } {
  const running = st.running ?? []
  if (flow === 'video_call') {
    const v = st.video ?? {}
    if (!running.includes('video')) return { n: 0, seen: 'VideoChat is not open yet.' }
    if (v.view === 'ended') return { n: 5, seen: 'The Call ended screen is showing.' }
    if (v.view === 'call') return { n: 4, seen: `The call screen is showing (${v.callState ?? 'in call'}).` }
    if (v.view === 'precall') return { n: 3, seen: 'The Ready to join screen is showing.' }
    if (v.selected === 'lily') return { n: 2, seen: 'Lily is selected and Start call is showing.' }
    return { n: 1, seen: 'VideoChat is open on the contacts list.' }
  }
  if (!running.includes('settings')) return { n: 0, seen: 'Settings is not open yet.' }
  if ((st.textStep ?? 0) >= 1) return { n: 3, seen: 'The text is larger.' }
  if (st.settings?.section === 'display') return { n: 2, seen: 'The Display panel is showing.' }
  return { n: 1, seen: 'Settings is open on General.' }
}

function flowStepOf(step: LessonStep): FlowStep | null {
  for (const flow of Object.keys(FLOW_TARGETS) as Flow[]) {
    const idx = fallbackPlan(flow).steps.findIndex((s) => s.id === step.id)
    if (idx >= 0) return { flow, n: idx + 1 }
  }
  const id = resolveTargetId(step.targetDescription)
  if (!id) return null
  for (const flow of Object.keys(FLOW_TARGETS) as Flow[]) {
    const idx = FLOW_TARGETS[flow].indexOf(id)
    if (idx >= 0) return { flow, n: idx + 1 }
  }
  return null
}

const friendly = (id: string): string => LABELS[id] ?? (id.split('.').pop() ?? id).replace(/_/g, ' ')

export interface StageTruthVerifierOpts extends StageTruthOpts {
  // The page must have been quiet this long before a verdict (the screen has settled; the tick should not flash early).
  settleMs?: number
  maxSettleMs?: number
  // A wrong click is only held against the learner for this long.
  misstepWindowMs?: number
}

export function createStageTruthVerifier(real: Verifier, getSource: () => StageTruthSource | null, opts: StageTruthVerifierOpts = {}): Verifier {
  const now = opts.now ?? Date.now
  const sleep = opts.sleep ?? realSleep
  const settleMs = opts.settleMs ?? 250
  const maxSettleMs = opts.maxSettleMs ?? 500
  const misstepWindowMs = opts.misstepWindowMs ?? 10_000
  const log = opts.log ?? ((): void => undefined)
  let seenSeq = 0

  return {
    async verify(req: VerifyRequest): Promise<Verdict> {
      const src = getSource()
      if (!('step' in req) || !src || !src.available()) return real.verify(req)
      const fs = flowStepOf(req.step)
      if (!fs) return real.verify(req)
      try {
        const started = now()
        let snap = await src.snapshot()
        while (now() - started < maxSettleMs) {
          const last = snap.events[snap.events.length - 1]
          if (!last || now() - last.t >= settleMs) break
          await sleep(60)
          snap = await src.snapshot()
        }
        const { n, seen } = progress(fs.flow, snap.state)
        const targetId = FLOW_TARGETS[fs.flow][fs.n - 1]
        const freshSeq = seenSeq
        seenSeq = Math.max(seenSeq, ...snap.events.map((e) => e.seq))
        if (n >= fs.n) {
          log(`verified ${req.step.id}: ${seen}`)
          return { completed: true, confidence: 1, uncertain: false, evidence: seen }
        }
        // Not done. A click on the wrong control since the last check is a misstep: name the right target (repair path).
        const wrong = [...snap.events]
          .reverse()
          .find((e) => e.type === 'click' && e.seq > freshSeq && e.id && e.id !== targetId && now() - e.t < misstepWindowMs)
        if (wrong?.id) {
          const label = LABELS[targetId] ?? 'the highlighted target'
          const hint = req.step.hints?.l2 ? `Not that one. ${req.step.hints.l2}` : `Not that one. ${req.step.instruction}`
          return {
            completed: false,
            confidence: 1,
            uncertain: false,
            evidence: `${seen} The last click was on ${friendly(wrong.id)}, not ${label}.`,
            learnerMisstep: `Clicked ${friendly(wrong.id)} instead of ${label}`,
            nextHint: hint,
          }
        }
        return { completed: false, confidence: 1, uncertain: false, evidence: `${seen} The step is not done yet.` }
      } catch (err) {
        log(`verify fell back to the real verifier: ${err instanceof Error ? err.message : String(err)}`)
        return real.verify(req)
      }
    },
  }
}

// ---------------------------------------------------------------- wiring
// One additive hook for services.ts: with ALONGSIDE_DEMO_DIRECTOR=1 the grounder and verifier are wrapped in place. The
// stage window registers itself later (setStageTruthSource); until then, and whenever it is gone, the real services answer.
export interface StageTruthHooks {
  log?: (msg: string) => void
  // With a lesson running, a click on the practice desktop asks the runner to verify at once (the screen watcher only
  // notices big changes; a row highlight can take seconds). The verifier above still decides, after the screen settles.
  lessonActive?: () => boolean
  verifyNow?: () => Promise<unknown>
  pollMs?: number
}
export function installStageTruth(s: Pick<Services, 'grounder' | 'verifier'>, hooks: StageTruthHooks = {}, env: NodeJS.ProcessEnv = process.env): void {
  if (!stageTruthEnabled(env)) return
  const real = { grounder: s.grounder, verifier: s.verifier }
  s.grounder = createStageTruthGrounder(real.grounder, getStageTruthSource, { log: hooks.log })
  s.verifier = createStageTruthVerifier(real.verifier, getStageTruthSource, { log: hooks.log })
  if (hooks.lessonActive && hooks.verifyNow) startClickWatch(hooks as Required<Pick<StageTruthHooks, 'lessonActive' | 'verifyNow'>> & StageTruthHooks)
}

function startClickWatch(h: Required<Pick<StageTruthHooks, 'lessonActive' | 'verifyNow'>> & StageTruthHooks): ReturnType<typeof setInterval> {
  let lastSeq = -1
  let busy = false
  const timer = setInterval(() => {
    const src = getStageTruthSource()
    if (busy || !src || !src.available()) return
    busy = true
    void (async () => {
      try {
        const { events } = await src.snapshot()
        const top = events.reduce((m, e) => Math.max(m, e.seq), 0)
        const fresh = lastSeq < 0 ? false : events.some((e) => e.seq > lastSeq && e.type === 'click' && e.id)
        lastSeq = top
        if (fresh && h.lessonActive()) {
          h.log?.('click on the practice desktop: verifying the step now')
          await h.verifyNow()
        }
      } catch (err) {
        h.log?.(`click watch: ${err instanceof Error ? err.message : String(err)}`)
      } finally {
        busy = false
      }
    })()
  }, h.pollMs ?? 120)
  ;(timer as { unref?: () => void }).unref?.()
  return timer
}

// The Electron side: the stage BrowserWindow, seen through the three page calls above (structural type: no electron import here).
export interface StageWindowLike {
  isDestroyed(): boolean
  isVisible(): boolean
  webContents: { isDestroyed(): boolean; executeJavaScript(code: string, userGesture?: boolean): Promise<unknown>; sendInputEvent(ev: { type: 'mouseMove' | 'mouseDown' | 'mouseUp'; x: number; y: number; button?: 'left'; clickCount?: number }): void }
}
export interface ElectronStageSource extends StageTruthSource {
  // Dev/debug only: a real input click (mouse move/down/up) at the centre of a ground id; falls back to element.click().
  debugClick(id: string): Promise<{ ok: boolean; via?: 'input' | 'element'; reason?: string }>
}

export function electronStageSource(getWin: () => StageWindowLike | null): ElectronStageSource {
  const win = (): StageWindowLike | null => {
    const w = getWin()
    return w && !w.isDestroyed() && !w.webContents.isDestroyed() ? w : null
  }
  const js = <T>(code: string): Promise<T> => {
    const w = win()
    if (!w) return Promise.reject(new Error('the practice desktop is gone'))
    return w.webContents.executeJavaScript(code, true) as Promise<T>
  }
  return {
    available: () => {
      const w = win()
      return Boolean(w && w.isVisible())
    },
    rects: () => js<Record<string, NormBox>>("window.__stage.rects({space:'screen'})"),
    snapshot: () => js<{ state: StageStateLite; events: StageEventLite[] }>('({state: window.__stage.state(), events: window.__stage.events().slice(-16)})'),
    async debugClick(id) {
      const w = win()
      if (!w) return { ok: false, reason: 'no stage window' }
      const q = JSON.stringify(id)
      const pt = await js<{ x: number; y: number } | null>(`(function(id){var r=__stage.rectOf(id); if(!r) return null; return {x:(r.xmin+r.xmax)/2/1000*innerWidth,y:(r.ymin+r.ymax)/2/1000*innerHeight};})(${q})`)
      if (!pt) return { ok: false, reason: `${id} is not visible` }
      const x = Math.round(pt.x)
      const y = Math.round(pt.y)
      const count = (): Promise<number> => js<number>('__stage.events().length')
      const before = await count()
      w.webContents.sendInputEvent({ type: 'mouseMove', x, y })
      w.webContents.sendInputEvent({ type: 'mouseDown', x, y, button: 'left', clickCount: 1 })
      await realSleep(90)
      w.webContents.sendInputEvent({ type: 'mouseUp', x, y, button: 'left', clickCount: 1 })
      await realSleep(160)
      if ((await count()) > before) return { ok: true, via: 'input' }
      await js(`(function(id){var e=document.querySelector('[data-ground-id="'+id+'"]'); if(e) e.click();})(${q})`)
      return { ok: true, via: 'element' }
    },
  }
}
