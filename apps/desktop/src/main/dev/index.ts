// QA test hooks. Inert unless ALONGSIDE_DEV_STAGE=1 (installed by one guarded line in src/main/index.ts).
// Separate dev HTTP on 127.0.0.1:${ALONGSIDE_DEV_PORT:-7778}: stage window + ground truth, overlay call log,
// outbound Gemini request log (spend, store flag) and network fault injection. Never logs headers or keys.
import http from 'node:http'
import { randomUUID } from 'node:crypto'
import { BrowserWindow, screen, systemPreferences } from 'electron'
import type { Services } from '../../shared/contracts'
import type { Annotation, ShotPurpose } from '../../shared/protocol'
import { grayGrid } from '../capture/change-score'
import { PROFILES } from '../capture/sizing'
import { ScreenChangeWatcher } from '../capture/watcher'
import type { ServiceContext } from '../context'
import { installFetchProbe } from './fetch-probe'
import { installReplay } from './replay'
import type { FaultSpec } from './fetch-probe'

export interface DevDeps {
  ctx: ServiceContext
  services: Services
}

const STAGE_URL = process.env.ALONGSIDE_STAGE_URL || `http://127.0.0.1:${process.env.STAGE_PORT || 5180}/index.html?still=1#desktop`
const MAX_BODY = 100_000

interface GroundTruthRect {
  id: string
  x: number
  y: number
  w: number
  h: number
  // Same box in normalised 0-1000 coordinates of the stage viewport (== primary display when fullscreen).
  norm: { xmin: number; ymin: number; xmax: number; ymax: number }
  text: string
}

// Runs inside the stage page. Visible = non-empty rect inside the viewport and not covered by another element.
const RECTS_JS = `(() => {
  const vw = window.innerWidth, vh = window.innerHeight
  const out = []
  for (const el of document.querySelectorAll('[data-ground-id]')) {
    const r = el.getBoundingClientRect()
    if (r.width < 2 || r.height < 2) continue
    const cs = getComputedStyle(el)
    if (cs.visibility === 'hidden' || cs.display === 'none' || Number(cs.opacity) === 0) continue
    const cx = Math.min(vw - 1, Math.max(0, r.left + r.width / 2)), cy = Math.min(vh - 1, Math.max(0, r.top + r.height / 2))
    if (r.right < 0 || r.bottom < 0 || r.left > vw || r.top > vh) continue
    const top = document.elementFromPoint(cx, cy)
    if (!top || !(top === el || el.contains(top) || top.contains(el))) continue
    const x1 = Math.max(0, r.left), y1 = Math.max(0, r.top), x2 = Math.min(vw, r.right), y2 = Math.min(vh, r.bottom)
    out.push({ id: el.getAttribute('data-ground-id'), x: x1, y: y1, w: x2 - x1, h: y2 - y1,
      norm: { xmin: x1 / vw * 1000, ymin: y1 / vh * 1000, xmax: x2 / vw * 1000, ymax: y2 / vh * 1000 },
      text: (el.getAttribute('aria-label') || el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 60) })
  }
  return { viewport: { w: vw, h: vh, dpr: window.devicePixelRatio }, rects: out }
})()`

function readJson(req: http.IncomingMessage): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    let size = 0
    const chunks: Buffer[] = []
    req.on('data', (c: Buffer) => {
      size += c.length
      if (size > MAX_BODY) return reject(new Error('body too large'))
      chunks.push(c)
    })
    req.on('end', () => {
      const text = Buffer.concat(chunks).toString('utf8')
      try {
        resolve(text ? (JSON.parse(text) as Record<string, unknown>) : {})
      } catch {
        reject(new Error('invalid JSON'))
      }
    })
    req.on('error', reject)
  })
}

export function installDev({ ctx, services }: DevDeps): void {
  // Record/replay needs no QA server; it is installed first so the probe's faults sit on top of it.
  installReplay(ctx.userDataDir, ctx.log)
  if (process.env.ALONGSIDE_DEV_STAGE !== '1') return
  const probe = installFetchProbe()
  type OverlayOp = { t: number; op: 'show' | 'clear' | 'caption' | 'chip'; annotations?: Annotation[]; ids?: string[]; text?: string; level?: number; speaker?: string }
  const overlayLog: OverlayOp[] = []
  const injectLog: { t: number; text: string; interrupt?: boolean }[] = []
  let stage: BrowserWindow | null = null

  // Record every command that reaches the overlay window, whoever sent it (dispatcher, lesson runner, agents): wrapping ctx.sendOverlay
  // sees them all, whereas wrapping services.overlay misses callers that kept their own reference to the method.
  const sendOverlay = ctx.sendOverlay.bind(ctx)
  ctx.sendOverlay = (cmd) => {
    const t = Date.now()
    if (cmd.type === 'show') overlayLog.push({ t, op: 'show', annotations: cmd.annotations })
    else if (cmd.type === 'clear') overlayLog.push({ t, op: 'clear', ids: cmd.ids })
    else if (cmd.type === 'caption') overlayLog.push({ t, op: 'caption', speaker: cmd.speaker, text: cmd.text })
    else overlayLog.push({ t, op: 'chip', level: cmd.level, text: cmd.label })
    sendOverlay(cmd)
  }
  const live = services.live
  const inject = live.inject.bind(live)
  live.inject = (text, opts) => {
    injectLog.push({ t: Date.now(), text, interrupt: opts?.interrupt })
    inject(text, opts)
  }

  const dockWindow = () => BrowserWindow.getAllWindows().find((w) => w.getTitle() === 'Alongside' && !w.isDestroyed())

  // Stage capture: when the OS refuses Screen Recording to this Electron build, the real Grounder/Verifier still see
  // exactly what the stage window paints (capturePage), same Shot shape. Mode: ALONGSIDE_DEV_CAPTURE=real|stage|auto (auto = stage
  // while the permission is not granted AND the stage window is open) or POST /dev/capture {mode}.
  let captureMode = (process.env.ALONGSIDE_DEV_CAPTURE ?? 'auto') as 'real' | 'stage' | 'auto'
  const screenPermission = () => (process.platform === 'darwin' ? systemPreferences.getMediaAccessStatus('screen') : 'granted')
  const useStageCapture = () => Boolean(stage && !stage.isDestroyed()) && (captureMode === 'stage' || (captureMode === 'auto' && screenPermission() !== 'granted'))
  const capture = services.capture
  const realGrab = capture.grab.bind(capture)
  const realLiveFrame = capture.liveFrame.bind(capture)
  const realWatch = capture.watch.bind(capture)
  async function stageShot(purpose: ShotPurpose) {
    const image = await stage!.webContents.capturePage()
    const physical = image.getSize()
    const width = Math.min(PROFILES[purpose].maxWidth, physical.width)
    const small = width < physical.width ? image.resize({ width, quality: 'good' }) : image
    const size = small.getSize()
    return {
      id: randomUUID(),
      displayId: screen.getPrimaryDisplay().id,
      widthPx: size.width,
      heightPx: size.height,
      scaleFactor: screen.getPrimaryDisplay().scaleFactor,
      jpegBase64: small.toJPEG(PROFILES[purpose].quality).toString('base64'),
      takenAt: Date.now(),
      overlayHidden: true,
    }
  }
  capture.grab = (purpose) => (useStageCapture() ? stageShot(purpose) : realGrab(purpose))
  capture.liveFrame = async () => {
    if (!useStageCapture()) return realLiveFrame()
    return { jpegBase64: (await stageShot('live')).jpegBase64, changeScore: 0 }
  }
  const stageWatcher = new ScreenChangeWatcher({
    async sample() {
      if (!useStageCapture()) return null
      const thumb = (await stage!.webContents.capturePage()).resize({ width: 128, height: 72 })
      const { width, height } = thumb.getSize()
      return grayGrid(thumb.toBitmap(), width, height, 'bgra')
    },
  })
  capture.watch = (on) => {
    const unsubReal = realWatch(on)
    const unsubStage = stageWatcher.subscribe(on)
    return () => {
      unsubReal()
      unsubStage()
    }
  }

  const stageEval = <T>(js: string): Promise<T> => {
    if (!stage || stage.isDestroyed()) return Promise.reject(new Error('stage window is not open'))
    return stage.webContents.executeJavaScript(js, true) as Promise<T>
  }

  async function openStage(): Promise<{ viewport: { w: number; h: number }; display: { w: number; h: number; scale: number }; content: { x: number; y: number; width: number; height: number } }> {
    const display = screen.getPrimaryDisplay()
    if (!stage || stage.isDestroyed()) {
      // A normal frameless window exactly on the work area (below the menu bar, beside the Dock): nothing covers it in a real desktop
      // capture, and its content bounds are known exactly, so ground truth maps to display-normalised coordinates without guessing.
      stage = new BrowserWindow({
        ...display.workArea,
        frame: false,
        show: false,
        resizable: false,
        movable: false,
        fullscreenable: false,
        hasShadow: false,
        backgroundColor: '#ffffff',
        title: 'Alongside QA stage',
        webPreferences: { sandbox: true, contextIsolation: true, nodeIntegration: false, backgroundThrottling: false },
      })
      stage.on('closed', () => {
        stage = null
      })
      await stage.loadURL(STAGE_URL)
      stage.setBounds(display.workArea)
      stage.setAlwaysOnTop(true, 'floating')
      stage.show()
    }
    stage.moveTop()
    const deadline = Date.now() + 8000
    while (Date.now() < deadline) {
      const ready = await stageEval<boolean>('Boolean(window.__stage || document.querySelector("[data-ground-id]"))').catch(() => false)
      if (ready) break
      await new Promise((r) => setTimeout(r, 150))
    }
    const viewport = await stageEval<{ w: number; h: number }>('({ w: window.innerWidth, h: window.innerHeight })')
    return { viewport, display: { w: display.bounds.width, h: display.bounds.height, scale: display.scaleFactor }, content: stage.getContentBounds() }
  }

  const server = http.createServer(async (req, res) => {
    const send = (status: number, body: unknown) => {
      res.writeHead(status, { 'content-type': 'application/json' })
      res.end(JSON.stringify(body))
    }
    try {
      const host = req.headers.host ?? ''
      if (req.headers.origin || !/^(127\.0\.0\.1|localhost)(:\d+)?$/.test(host)) return send(403, { error: 'forbidden' })
      const url = new URL(req.url ?? '/', `http://${host}`)
      const route = `${req.method} ${url.pathname}`
      switch (route) {
        case 'GET /dev/health':
          return send(200, { ok: true, stageOpen: Boolean(stage && !stage.isDestroyed()) })
        case 'POST /dev/stage/open':
          return send(200, await openStage())
        case 'POST /dev/stage/close':
          if (stage && !stage.isDestroyed()) stage.destroy()
          stage = null
          return send(200, { ok: true })
        case 'GET /dev/stage/rects':
          return send(200, await stageEval<{ viewport: unknown; rects: GroundTruthRect[] }>(RECTS_JS))
        case 'GET /dev/stage/screen-rects': {
          // __stage.rects() (viewport-normalised) mapped to display-normalised through the window's exact content bounds.
          if (!stage || stage.isDestroyed()) return send(409, { error: 'stage window is not open' })
          const d = screen.getPrimaryDisplay().bounds
          const cb = stage.getContentBounds()
          const vp = await stageEval<{ w: number; h: number }>('({ w: window.innerWidth, h: window.innerHeight })')
          const raw = await stageEval<Record<string, { xmin: number; ymin: number; xmax: number; ymax: number }>>('JSON.parse(JSON.stringify(window.__stage ? window.__stage.rects() : {}))')
          const fx = (n: number) => ((cb.x + (n / 1000) * cb.width - d.x) / d.width) * 1000
          const fy = (n: number) => ((cb.y + (n / 1000) * cb.height - d.y) / d.height) * 1000
          const rects = Object.fromEntries(Object.entries(raw).map(([id, b]) => [id, { xmin: fx(b.xmin), ymin: fy(b.ymin), xmax: fx(b.xmax), ymax: fy(b.ymax) }]))
          return send(200, { rects, content: cb, viewport: vp, sizeMatches: Math.abs(vp.w - cb.width) <= 1 && Math.abs(vp.h - cb.height) <= 1 })
        }
        case 'GET /dev/stage/catalog':
          return send(200, await stageEval<unknown>('JSON.parse(JSON.stringify(window.__stage ? window.__stage.catalog() : []))'))
        case 'GET /dev/stage/flows':
          return send(200, await stageEval<unknown>('JSON.parse(JSON.stringify(window.STAGE_FLOWS || null))'))
        case 'POST /dev/stage/call': {
          // Only functions on window.__stage (setStep, deliverScam, ...); no arbitrary script.
          const body = await readJson(req)
          const fn = String(body.fn ?? '')
          if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(fn)) return send(400, { error: 'bad fn' })
          const args = JSON.stringify(Array.isArray(body.args) ? body.args : [])
          const result = await stageEval<unknown>(`(async () => { const f = window.__stage && window.__stage[${JSON.stringify(fn)}]; if (typeof f !== 'function') throw new Error('no __stage.' + ${JSON.stringify(fn)}); const r = await f(...${args}); return r === undefined ? null : JSON.parse(JSON.stringify(r)) })()`)
          return send(200, { result })
        }
        case 'POST /dev/dock': {
          const body = await readJson(req)
          const win = dockWindow()
          if (win) {
            if (body.visible === false) win.hide()
            else win.showInactive()
          }
          return send(200, { ok: Boolean(win) })
        }
        case 'GET /dev/dock/text': {
          const win = dockWindow()
          if (!win) return send(404, { error: 'no dock window' })
          return send(200, { text: await win.webContents.executeJavaScript('document.body.innerText', true) })
        }
        case 'POST /dev/dock/click': {
          // Finds a dock button by visible text / aria-label. Default: a TRUSTED mouse click through the input pipeline
          // (what a real user produces). {synthetic:true}: a script-made el.click() (isTrusted=false), to prove it is ignored.
          const body = await readJson(req)
          const win = dockWindow()
          if (!win) return send(404, { error: 'no dock window' })
          const needle = JSON.stringify(String(body.text ?? ''))
          const synthetic = body.synthetic === true
          const found = await win.webContents.executeJavaScript(
            `(() => { const n = ${needle}.toLowerCase(); const els = [...document.querySelectorAll('button,[role=button],[role=switch],[role=checkbox],[role=tab],input[type=checkbox]')]; const label = (e) => (e.getAttribute('aria-label') || e.innerText || e.value || '').trim(); const el = els.find(e => label(e).toLowerCase() === n) || els.find(e => label(e).toLowerCase().includes(n)); if (!el) return null; el.scrollIntoView({ block: 'center' }); const r = el.getBoundingClientRect(); if (${synthetic}) el.click(); return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2), label: label(el).slice(0, 60) } })()`,
            true,
          )
          if (!found) return send(404, { clicked: null })
          if (!synthetic) {
            const { x, y } = found as { x: number; y: number }
            win.webContents.sendInputEvent({ type: 'mouseMove', x, y })
            win.webContents.sendInputEvent({ type: 'mouseDown', x, y, button: 'left', clickCount: 1 })
            win.webContents.sendInputEvent({ type: 'mouseUp', x, y, button: 'left', clickCount: 1 })
          }
          return send(200, { clicked: (found as { label: string }).label, synthetic })
        }
        case 'POST /dev/dock/api': {
          // Calls a read-only / allow-listed function of window.alongside in the dock renderer (the same preload API the UI uses).
          const body = await readJson(req)
          const apiPath = String(body.path ?? '')
          const allowed = /^(permissions\.status|files\.(list|status)|getSettings|getState|showtime\.(state|start|stop|next|prev|pause)|learner\.snapshot|agency\.status)$/
          if (!allowed.test(apiPath)) return send(400, { error: `not allowed: ${apiPath}` })
          const win = dockWindow()
          if (!win) return send(404, { error: 'no dock window' })
          const args = JSON.stringify(Array.isArray(body.args) ? body.args : [])
          const result = await win.webContents.executeJavaScript(
            `(async () => { const parts = ${JSON.stringify(apiPath)}.split('.'); let o = window.alongside; for (const p of parts.slice(0, -1)) o = o && o[p]; const f = o && o[parts[parts.length - 1]]; if (typeof f !== 'function') return { __missing: true }; const r = await f.apply(o, ${args}); return r === undefined ? null : JSON.parse(JSON.stringify(r)) })()`,
            true,
          )
          return send(200, { result })
        }
        case 'GET /dev/learner':
          return send(200, services.learner.snapshot())
        case 'GET /dev/inject/log':
          return send(200, injectLog)
        case 'POST /dev/inject/log/clear':
          injectLog.length = 0
          return send(200, { ok: true })
        case 'GET /dev/overlay/log':
          return send(200, overlayLog)
        case 'POST /dev/overlay/log/clear':
          overlayLog.length = 0
          return send(200, { ok: true })
        case 'GET /dev/fetch/log':
          return send(200, probe.log)
        case 'POST /dev/fetch/log/clear':
          probe.log.length = 0
          return send(200, { ok: true })
        case 'POST /dev/fault': {
          const body = await readJson(req)
          probe.setFault(body as unknown as FaultSpec)
          return send(200, { ok: true, fault: probe.getFault() })
        }
        case 'GET /dev/fault':
          return send(200, { fault: probe.getFault() })
        case 'POST /dev/capture': {
          const body = await readJson(req)
          if (body.mode === 'real' || body.mode === 'stage' || body.mode === 'auto') captureMode = body.mode
          return send(200, { mode: captureMode, usingStage: useStageCapture() })
        }
        case 'GET /dev/services':
          return send(200, {
            screenPermission: screenPermission(),
            captureMode,
            usingStageCapture: useStageCapture(),
            mockEnv: process.env.ALONGSIDE_MOCK === '1',
            perService: Object.fromEntries(Object.keys(services).map((n) => [n, process.env[`ALONGSIDE_MOCK_${n.toUpperCase()}`] === '1'])),
            keyPresent: Boolean(process.env.GEMINI_API_KEY),
          })
        default:
          return send(404, { error: 'not found' })
      }
    } catch (err) {
      send(500, { error: err instanceof Error ? err.message : String(err) })
    }
  })
  const port = Number(process.env.ALONGSIDE_DEV_PORT || 7778)
  server.listen(port, '127.0.0.1', () => ctx.log('dev', `qa hooks on 127.0.0.1:${port}`))
  server.on('error', (err) => ctx.log('dev', 'server error:', err.message))
}
