// Executes Showtime actions against the REAL app: the overlay controller, the state store (dock UI), settings, the
// level engine, the learner store, the dispatcher and the confirm broker. Scripted mode injects fixed results where a
// model would be called (boxes come from the stage's own ground truth, recorded scam report, recorded file search).
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { app } from 'electron'
import { IPC } from '../../shared/ipc'
import type { Services } from '../../shared/contracts'
import { unwrapSnippet } from '../../shared/files'
import { HELP_LEVEL_LABELS, ScamReportSchema, type Annotation, type AttemptRecord, type NormBox, type NormPoint, type PersonaId, type ScamReport } from '../../shared/protocol'
import type { Settings } from '../../shared/settings'
import type { ShowtimeCue, ShowtimeMode } from '../../shared/showtime'
import { lastAuditLine } from '../agency/audit'
import type { ConfirmBroker } from '../confirm'
import type { ServiceContext } from '../context'
import type { Dispatch } from '../tools/dispatcher'
import type { Narrator } from './narration'
import { line, resolveText } from './script'
import type { StageWindow } from './stage-window'
import type { Action, AnnSpec, BoxRef, TourSettingsPatch } from './types'

export interface DriverDeps {
  ctx: ServiceContext
  services: Services
  dispatch: Dispatch
  confirm: ConfirmBroker
  stage: () => StageWindow | null
  narrator: Narrator
  mode: ShowtimeMode
  // Settings as they were before the tour: the baseline each chapter returns to, and what is restored at the end.
  settingsBaseline: Settings
  dockStopBox: () => Promise<NormBox | null>
  log: (msg: string) => void
}

const CHIP_ID = 'showtime-scam'
const SCAM_MESSAGE = 'messages.msg.scam.0'
const TOUR_KEYS = ['glass', 'glassOpacity', 'dyslexiaFont', 'textScale', 'theme', 'highContrast'] as const
const AGENCY_URL = process.env.ALONGSIDE_SHOWTIME_OPEN_URL || 'https://www.ageuk.org.uk'

const center = (b: NormBox): NormPoint => ({ x: (b.xmin + b.xmax) / 2, y: (b.ymin + b.ymax) / 2 })
const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

async function readJson<T>(rel: string): Promise<T> {
  const file = path.join(process.env.ALONGSIDE_SHOWTIME_ASSETS || path.join(app.getAppPath(), 'assets/showtime'), rel)
  return JSON.parse(await readFile(file, 'utf8')) as T
}

export interface Driver {
  exec(action: Action): Promise<void>
  pauseAudio(): void
  resumeAudio(): void
  // End of the tour: stop audio, clear what we drew, restore settings. (The stage and profile are the glue's job.)
  teardown(): Promise<void>
}

export function createDriver(deps: DriverDeps): Driver {
  const { ctx, services, dispatch, confirm, narrator, mode, log } = deps
  const { state, settings } = ctx
  const cue = (c: ShowtimeCue): void => ctx.sendDock(IPC.showtimeCue, c)
  const boxCache = new Map<string, NormBox>()
  let phaseTimer: NodeJS.Timeout | null = null
  let agencyCall: Promise<unknown> | null = null
  let scamReport: ScamReport | null = null

  const muted = (): boolean => process.env.ALONGSIDE_SHOWTIME_MUTE === '1' || settings.get().textOnly

  // ---------- resolving targets to boxes (stage ground truth) ----------
  async function resolveBox(target: string, rects: Record<string, NormBox>): Promise<NormBox | null> {
    if (target === '@dock.stop') {
      const b = await deps.dockStopBox()
      if (b) boxCache.set(target, b)
      return b ?? boxCache.get(target) ?? null
    }
    const live = rects[target]
    if (live) {
      boxCache.set(target, live)
      return live
    }
    // A target that was just clicked may already be gone (the next screen replaced it): use where it was.
    return boxCache.get(target) ?? null
  }

  async function boxesFor(ref: BoxRef, rects: Record<string, NormBox>): Promise<NormBox[]> {
    const stage = deps.stage()
    if (ref.phrase && stage) return stage.phraseBoxes(ref.target, ref.phrase)
    const b = await resolveBox(ref.target, rects)
    return b ? [b] : []
  }

  async function toAnnotations(specs: AnnSpec[]): Promise<Annotation[]> {
    const stage = deps.stage()
    const rects = stage ? await stage.rects() : {}
    const out: Annotation[] = []
    for (const s of specs) {
      const id = `st-${s.id}`
      switch (s.kind) {
        case 'ring': {
          const box = await resolveBox(s.target, rects)
          if (box) out.push({ id, kind: 'ring', tone: s.tone ?? 'guide', box, label: s.label, step: s.step })
          else log(`ring ${s.id}: ${s.target} not visible`)
          break
        }
        case 'arrow': {
          const box = await resolveBox(s.target, rects)
          if (box) out.push({ id, kind: 'arrow', tone: s.tone ?? 'guide', to: box })
          break
        }
        case 'tick': {
          const box = await resolveBox(s.target, rects)
          if (box) out.push({ id, kind: 'tick', tone: 'success', box, ok: s.ok !== false })
          break
        }
        case 'spotlight': {
          const box = await resolveBox(s.target, rects)
          if (box) out.push({ id, kind: 'spotlight', tone: 'guide', box })
          break
        }
        case 'highlight': {
          // In live mode the real report draws its own highlights.
          if (mode === 'live' && s.id.startsWith('flag-')) break
          const boxes = (await Promise.all(s.boxes.map((r) => boxesFor(r, rects)))).flat()
          if (boxes.length) out.push({ id, kind: 'highlightText', tone: s.tone ?? 'danger', boxes, note: s.note })
          else log(`highlight ${s.id}: no boxes`)
          break
        }
        case 'bubble': {
          const box = await resolveBox(s.target, rects)
          if (box) out.push({ id, kind: 'bubble', tone: s.tone ?? 'guide', at: { x: (box.xmin + box.xmax) / 2, y: box.ymax }, text: s.text })
          break
        }
        case 'bubbleAt':
          out.push({ id, kind: 'bubble', tone: s.tone ?? 'guide', at: s.at, text: s.text })
          break
        case 'ringBox':
          out.push({ id, kind: 'ring', tone: s.tone ?? 'guide', box: s.box, label: s.label })
          break
        case 'ghost': {
          const pts: NormPoint[] = []
          for (const t of s.targets) {
            const b = await resolveBox(t, rects)
            if (b) pts.push(center(b))
          }
          if (pts.length) out.push({ id, kind: 'ghostCursor', tone: 'guide', path: pts, pressAtEnd: s.pressAtEnd })
          break
        }
      }
    }
    return out
  }

  // ---------- helpers ----------
  function say(lineId: string): Promise<void> {
    const l = line(lineId)
    const text = resolveText(l)
    state.addCaption('assistant', text, true)
    services.overlay.caption('assistant', text, true)
    state.patch({ phase: 'speaking' })
    if (phaseTimer) clearTimeout(phaseTimer)
    phaseTimer = setTimeout(() => state.patch({ phase: 'live' }), l.durationMs)
    return (muted() ? Promise.resolve(null) : narrator.clip(l.id, text)).then((clip) => {
      cue({ type: 'say', id: l.id, text, persona: l.persona, ...(clip ? { audioBase64: clip.base64, mime: clip.mime } : {}) })
    })
  }

  function caption(speaker: 'user' | 'assistant' | 'system', text: string): void {
    state.addCaption(speaker, text, true)
    services.overlay.caption(speaker, text, true)
  }

  function setPersona(id: PersonaId): void {
    if (state.get().persona !== id || settings.get().persona !== id) {
      settings.patch({ persona: id })
      state.patch({ persona: id })
    }
  }

  function patchTourSettings(patch: TourSettingsPatch): void {
    const current = settings.get() as unknown as Record<string, unknown>
    const usable: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(patch)) {
      if (k in current) usable[k] = v
      else log(`setting ${k} is not in this build: skipped`)
    }
    if (Object.keys(usable).length) settings.patch(usable)
  }

  // `all` (end of the tour): EXACT prior settings, every key the tour or the actions it triggered changed (agency,
  // captions, persona...) goes back. Per chapter: only the look-and-feel keys the tour flips.
  function restoreTourSettings(all = false): void {
    const base = deps.settingsBaseline as unknown as Record<string, unknown>
    const now = settings.get() as unknown as Record<string, unknown>
    const back: Record<string, unknown> = {}
    const keys: readonly string[] = all ? Object.keys(base) : TOUR_KEYS
    for (const k of keys) if (k in base && JSON.stringify(base[k]) !== JSON.stringify(now[k])) back[k] = base[k]
    if (Object.keys(back).length) settings.patch(back)
  }

  function setLevel(to: 1 | 2 | 3 | 4): void {
    state.patch({ level: to })
    services.overlay.chip(to, HELP_LEVEL_LABELS[to])
  }

  function chip(status: 'running' | 'done' | 'error', summary: string, report?: ScamReport): void {
    const prev = state.get().agents.find((a) => a.id === CHIP_ID)
    state.upsertAgent({
      id: CHIP_ID,
      kind: 'scam_check',
      title: 'Checking this message',
      status,
      startedAt: prev?.startedAt ?? Date.now(),
      summary,
      ...(report ? { result: { kind: 'scam_check' as const, report } } : {}),
    })
  }

  // ---------- real scam analysis (live mode only) ----------
  async function runLiveScam(): Promise<void> {
    const stage = deps.stage()
    chip('running', 'Checking this message…')
    try {
      const text = stage ? await stage.messageText(SCAM_MESSAGE) : ''
      const report = await services.scam.analyze({ text }, { onProgress: (m) => chip('running', m) })
      chip('done', report.verdict === 'likely_scam' ? 'Likely a scam. Do not tap the link.' : report.advice[0] ?? 'Done', report)
      const specs: Annotation[] = []
      let n = 0
      for (const f of report.redFlags.slice(0, 4)) {
        const boxes = stage ? await stage.phraseBoxes(SCAM_MESSAGE, f.phrase) : []
        if (boxes.length) specs.push({ id: `st-live-flag-${n++}`, kind: 'highlightText', tone: 'danger', boxes, note: f.why })
      }
      if (specs.length) services.overlay.show(specs)
    } catch (err) {
      chip('error', 'I could not finish checking this message.')
      log(`live scam check failed: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  async function seedAttempts(): Promise<void> {
    const snap = services.learner.snapshot()
    if (snap.attempts.some((a) => a.id.startsWith('showtime-'))) return
    const day = 86_400_000
    const now = Date.now()
    const base = { skillId: 'video_call' as const, lessonId: 'video_call', completed: true, safetyFlag: false, anxietyPhrase: false, teachBackScore: 0.8 }
    const rows: Array<Pick<AttemptRecord, 'id' | 'levelAtStart' | 'levelAtEnd' | 'hintsUsed' | 'errors' | 'stalls' | 'confidence' | 'clean'> & { ago: number }> = [
      { id: 'showtime-1', ago: 3, levelAtStart: 1, levelAtEnd: 2, hintsUsed: 5, errors: 1, stalls: 1, confidence: 2, clean: false },
      { id: 'showtime-2', ago: 2, levelAtStart: 2, levelAtEnd: 2, hintsUsed: 3, errors: 0, stalls: 0, confidence: 3, clean: true },
      { id: 'showtime-3', ago: 1, levelAtStart: 2, levelAtEnd: 2, hintsUsed: 1, errors: 0, stalls: 0, confidence: 4, clean: true },
    ]
    for (const { ago, ...r } of rows) {
      const endedAt = now - ago * day
      await services.learner.recordAttempt({ ...base, ...r, startedAt: endedAt - 4 * 60_000, endedAt })
    }
  }

  async function forgetLine(match: string): Promise<void> {
    const r = await services.learner.editMarkdown({ op: 'read' })
    const lines = r.content.split('\n')
    const i = lines.findIndex((l) => l.includes(match))
    if (i < 0) {
      log(`profile.forget: no line containing "${match}"`)
      return
    }
    const forgotten = lines[i].replace(/^\s*[-*]\s+/, '').trim()
    lines.splice(i, 1)
    const w = await services.learner.editMarkdown({ op: 'write', content: lines.join('\n'), revision: r.revision })
    if (!w.ok) log('profile.forget: the file changed underneath, nothing was removed')
    cue({ type: 'profile-refresh' })
    if (w.ok) caption('system', `Forgotten: “${forgotten}”`)
  }

  async function filesSearch(query: string): Promise<void> {
    type Hit = { name: string; folder?: string; path: string; snippet: string }
    let hit: Hit | null = null
    if (mode === 'live') {
      const res = (await dispatch('search_files', { query, k: 3 }, 'debug')) as { ok?: boolean; results?: Hit[] }
      hit = res.ok && res.results?.length ? res.results[0] : null
    } else {
      const fixture = await readJson<{ results: Hit[] }>('fixtures/files-search.json')
      hit = fixture.results[0] ?? null
    }
    if (!hit) {
      caption('assistant', 'I could not find that in the folders you chose.')
      return
    }
    const snippet = unwrapSnippet(hit.snippet).replace(/\s+/g, ' ').trim().slice(0, 140)
    services.overlay.show([
      { id: 'st-file-name', kind: 'bubble', tone: 'success', at: { x: 500, y: 330 }, text: `Found: ${hit.name}` },
      { id: 'st-file-path', kind: 'bubble', tone: 'guide', at: { x: 500, y: 470 }, text: `${hit.path} — “${snippet}”` },
    ])
  }

  async function agencyAudit(): Promise<void> {
    let text = `Logged: opened ${new URL(AGENCY_URL).host} for you, after you said yes.`
    try {
      const raw = await lastAuditLine(ctx.userDataDir)
      if (raw) {
        const e = JSON.parse(raw) as { tool?: string; decision?: string; host?: string; label?: string; dryRun?: boolean }
        text = `Logged: ${e.tool ?? 'open_for_me'} · ${e.decision ?? 'allowed'} · ${e.host ?? e.label ?? new URL(AGENCY_URL).host}${e.dryRun ? ' · practice run' : ''}`
      }
    } catch {
      // keep the plain sentence
    }
    services.overlay.show([{ id: 'st-audit', kind: 'bubble', tone: 'success', at: { x: 500, y: 300 }, text }])
  }

  // ---------- the action switch ----------
  async function exec(action: Action): Promise<void> {
    const stage = deps.stage()
    switch (action.type) {
      case 'baseline': {
        if (phaseTimer) clearTimeout(phaseTimer)
        phaseTimer = null
        cue({ type: 'stop-audio' })
        confirm.cancel()
        services.overlay.clear()
        services.overlay.caption('assistant', '', true)
        boxCache.clear()
        scamReport = null
        stage?.show()
        setPersona(action.persona)
        restoreTourSettings()
        if (state.get().level !== 2) setLevel(2)
        state.patch({ agents: [], skill: undefined, captions: [], phase: 'live' })
        cue({ type: 'view', view: 'now' })
        return
      }
      case 'stage.go':
        boxCache.clear()
        await stage?.go(action.route)
        return
      case 'stage.click':
        await stage?.click(action.target)
        return
      case 'stage.deliverScam':
        await stage?.deliverScam()
        return
      case 'stage.hide':
        stage?.hide()
        return
      case 'stage.show':
        stage?.show()
        return
      case 'ann.show':
        services.overlay.show(await toAnnotations(action.specs))
        return
      case 'ann.clear':
        services.overlay.clear(action.ids?.map((i) => `st-${i}`))
        return
      case 'say':
        await say(action.line)
        return
      case 'caption':
        caption(action.speaker, action.text)
        return
      case 'phase':
        state.patch({ phase: action.phase })
        return
      case 'persona':
        setPersona(action.id)
        return
      case 'level': {
        const from = state.get().level
        if (action.scope === 'attempt') {
          try {
            const now = Date.now()
            const decision = services.levels.evaluateAttempt(
              { id: 'showtime-eval', skillId: 'video_call', lessonId: 'video_call', startedAt: now - 120_000, endedAt: now, levelAtStart: 2, levelAtEnd: 2, completed: true, hintsUsed: 0, errors: 0, stalls: 0, safetyFlag: false, anxietyPhrase: false, teachBackScore: 0.8, confidence: 4, clean: true },
              { level: 2, streakClean: 1, lastSeen: now - 86_400_000, nextReview: null },
              { demoMode: true, now },
            )
            log(`level engine: ${decision.change} to L${decision.state.level} (${decision.reason})`)
          } catch (err) {
            log(`level engine probe failed: ${err instanceof Error ? err.message : String(err)}`)
          }
        }
        ctx.bus.emit('level:changed', { skillId: 'video_call', from, to: action.to, reason: action.reason, scope: action.scope })
        return
      }
      case 'skill':
        state.patch({ skill: action.skill ?? undefined })
        return
      case 'settings':
        patchTourSettings(action.patch)
        return
      case 'agent': {
        if (action.op === 'start') {
          if (mode === 'live') void runLiveScam()
          else chip('running', action.text ?? 'Checking this message…')
        } else if (mode !== 'live') {
          if (action.op === 'progress') chip('running', action.text ?? '')
          else {
            scamReport ??= ScamReportSchema.parse(await readJson<unknown>('fixtures/scam-report.json'))
            chip('done', action.text ?? 'Done', scamReport)
          }
        }
        return
      }
      case 'dock.view':
        cue({ type: 'view', view: action.view })
        return
      case 'dock.chat':
        cue({ type: 'chat', id: action.id, role: action.role, text: action.text })
        caption(action.role, action.text)
        return
      case 'profile.forget':
        await forgetLine(action.match)
        return
      case 'progress.seed':
        await seedAttempts()
        return
      case 'agency.request': {
        if (settings.get().agency === 'off') settings.patch({ agency: 'ask_each' })
        agencyCall = dispatch('open_for_me', { kind: 'url', value: AGENCY_URL }, 'debug').catch((err: unknown) => ({ error: String(err) }))
        return
      }
      case 'agency.approve': {
        // The visible "demo approve" step: in real use this is the user's own click on the real modal.
        const pending = state.get().pendingConfirm
        if (!pending) {
          log('agency.approve: no confirmation is pending')
          return
        }
        confirm.answer(pending.id, pending.options[0])
        const result = await Promise.race([agencyCall ?? Promise.resolve(null), sleep(3000).then(() => 'timeout')])
        log(`open_for_me result: ${JSON.stringify(result)}`)
        return
      }
      case 'agency.audit':
        await agencyAudit()
        return
      case 'files.search':
        await filesSearch(action.query)
        return
    }
  }

  return {
    async exec(action) {
      await exec(action)
    },
    pauseAudio: () => cue({ type: 'pause-audio' }),
    resumeAudio: () => cue({ type: 'resume-audio' }),
    async teardown() {
      if (phaseTimer) clearTimeout(phaseTimer)
      phaseTimer = null
      cue({ type: 'stop-audio' })
      confirm.cancel()
      services.overlay.clear()
      services.overlay.caption('assistant', '', true)
      restoreTourSettings(true)
      state.patch({ agents: [], skill: undefined, captions: [], phase: settings.get().wakeEnabled ? 'listening_for_name' : 'asleep' })
      const basePersona = deps.settingsBaseline.persona
      if (settings.get().persona !== basePersona) {
        settings.patch({ persona: basePersona })
        state.patch({ persona: basePersona })
      }
      if (state.get().level !== 2) setLevel(2)
    },
  }
}
