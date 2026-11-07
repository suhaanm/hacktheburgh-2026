// Real-window verification of the overlay + capture on this Mac. Run ONLY via real-check.sh (electron-lock).
// Starts the built app (real capture + overlay, wake spotter off), shows the STAGE page in a second window, then:
//  1. draws a ring on a known stage element and measures where the ring really landed (mapping + rendering)
//  2. content protection: the ring must be missing from a desktopCapturer grab but present in the overlay's own PNG
//  3. click-through: a synthetic OS click through the overlay must reach the window underneath
//  4. point_at via the debug HTTP API against the real grounder (composite PNG for eyeballing)
//  5. ALONGSIDE_OVERLAY_CAPTURABLE=1 mode: 'live' grabs show the overlay, ground/verify grabs do not; and a native
//     full-screen app on its own Space still shows the overlay on top.
import { spawn, execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const repo = path.resolve(here, '../../../..')
const outDir = path.resolve(process.env.OVERLAY_SHOTS ?? path.join(repo, 'docs/overlay-shots'))
const electron = path.join(repo, 'node_modules/.bin/electron')
const tool = path.join(here, 'window-tool.cjs')
let stageUrl = process.env.STAGE_URL ?? 'http://127.0.0.1:5180/index.html?still=1#video/call-screen'
const port = Number(process.env.ALONGSIDE_DEBUG_PORT ?? 7790)
const base = `http://127.0.0.1:${port}`
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'overlay-real-'))
const userData = path.join(tmp, 'userdata')
fs.mkdirSync(userData, { recursive: true })
fs.mkdirSync(outDir, { recursive: true })
fs.writeFileSync(path.join(userData, 'settings.json'), JSON.stringify({ wakeEnabled: false, captions: true, bigAnnotations: true }))

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const children = new Set()
const results = { startedAt: new Date().toISOString(), checks: {} }
const log = (...a) => console.log('[real-check]', ...a)

function spawnLogged(cmd, args, env = {}) {
  const child = spawn(cmd, args, { cwd: repo, env: { ...process.env, ...env }, stdio: ['ignore', 'pipe', 'pipe'], detached: false })
  children.add(child)
  child.lines = []
  const onData = (d) => d.toString().split('\n').filter(Boolean).forEach((l) => child.lines.push(l))
  child.stdout.on('data', onData)
  child.stderr.on('data', onData)
  child.on('exit', () => children.delete(child))
  return child
}
const killAll = () => children.forEach((c) => c.kill('SIGTERM'))
process.on('exit', killAll)
process.on('SIGTERM', () => process.exit(143))

async function waitFor(fn, ms, what) {
  const t0 = Date.now()
  while (Date.now() - t0 < ms) {
    try {
      const v = await fn()
      if (v) return v
    } catch {
      /* retry */
    }
    await sleep(250)
  }
  throw new Error(`timed out waiting for ${what}`)
}

async function runTool(...args) {
  return new Promise((resolve) => {
    const c = spawn(electron, [tool, ...args], { cwd: repo, stdio: ['ignore', 'pipe', 'pipe'] })
    let out = ''
    c.stdout.on('data', (d) => (out += d))
    c.stderr.on('data', (d) => (out += d))
    c.on('exit', () => {
      const line = out.split('\n').find((l) => l.startsWith('[window-tool] ') && l.includes('{'))
      resolve(line ? JSON.parse(line.slice('[window-tool] '.length)) : { error: out.slice(-300) })
    })
  })
}

const post = (route, body) => fetch(base + route, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }).then((r) => r.json())
async function save(route, file) {
  const res = await fetch(base + route)
  const buf = Buffer.from(await res.arrayBuffer())
  fs.writeFileSync(file, buf)
  return { file, bytes: buf.length, headers: Object.fromEntries(res.headers) }
}

// Element rect (page CSS px) -> normalised box on the display, through the stage window's real on-screen origin.
const ringBoxFor = (el, stageGeo) => ({
  xmin: Math.max(0, ((stageGeo.origin.x + el.x) / stageGeo.display.w) * 1000),
  ymin: Math.max(0, ((stageGeo.origin.y + el.y) / stageGeo.display.h) * 1000),
  xmax: Math.min(1000, ((stageGeo.origin.x + el.x + el.w) / stageGeo.display.w) * 1000),
  ymax: Math.min(1000, ((stageGeo.origin.y + el.y + el.h) / stageGeo.display.h) * 1000),
})

async function startApp(extraEnv = {}) {
  const app = spawnLogged(electron, ['.'], { ALONGSIDE_USERDATA: userData, ALONGSIDE_DEBUG_PORT: String(port), ...extraEnv })
  await waitFor(async () => (await fetch(base + '/health')).ok, 30000, 'app /health')
  await sleep(2500) // overlay window + renderer ready
  return app
}
async function stopApp(app) {
  app.kill('SIGTERM')
  await sleep(1200)
  if (app.exitCode === null) app.kill('SIGKILL')
  await sleep(500)
}

// The stage is a static page: start our own server if nobody is serving it.
const stageReachable = await fetch(stageUrl.split('#')[0]).then((r) => r.ok).catch(() => false)
if (!stageReachable) {
  const stagePort = '5195'
  spawnLogged('node', [path.join(repo, 'scripts/stage-server.mjs')], { STAGE_PORT: stagePort })
  stageUrl = stageUrl.replace(/:\d+\//, `:${stagePort}/`)
  await waitFor(() => fetch(stageUrl.split('#')[0]).then((r) => r.ok), 10000, 'stage server')
  log('started own stage server on', stagePort)
}
const TARGET = process.env.STAGE_TARGET ?? 'video.call.mic'
// The point_at target must be visible: the call controls sit behind the macOS Dock on a full-display stage window.
const POINT_ID = process.env.POINT_ID ?? 'desk.icon.settings'
const skip = new Set((process.env.REAL_CHECK_SKIP ?? '').split(',').filter(Boolean))
try {
  // ---- stage window ----
  const stage = spawnLogged(electron, [tool, 'stage', stageUrl, tmp])
  await waitFor(() => fs.existsSync(path.join(tmp, 'rects.json')), 45000, 'stage window').catch((e) => {
    throw new Error(`${e.message}; stage output: ${stage.lines.slice(-6).join(' | ')}`)
  })
  const stageGeo = JSON.parse(fs.readFileSync(path.join(tmp, 'rects.json'), 'utf8'))
  const { viewport, rects } = stageGeo
  const el = rects[TARGET]
  if (!rects[POINT_ID]) log('warning: point id not on stage', POINT_ID)
  results.stage = { url: stageUrl, viewport, origin: stageGeo.origin, display: stageGeo.display, target: TARGET, element: el ?? null, groundIds: Object.keys(rects).length }
  log('stage ready', JSON.stringify(results.stage))
  if (!el) throw new Error(`stage has no element ${TARGET}`)

  // ---- pass 1: default (content protection on) ----
  let app = await startApp()
  const health = await (await fetch(base + '/health')).json()
  results.app = health

  const ring = { id: 'check-ring', kind: 'ring', tone: 'guide', box: ringBoxFor(el, stageGeo) }
  if (!skip.has('ring')) {
  await post('/overlay', { cmd: { type: 'show', annotations: [ring] } })
  await sleep(1200)
  const overlay = await save('/overlay.png', path.join(outDir, 'real-ring-overlay.png'))
  const protectedShot = await save('/shot?purpose=ground', path.join(outDir, 'real-ring-ground-shot.jpg'))
  const analyze = await runTool('analyze', overlay.file, path.join(tmp, 'rects.json'), TARGET, '4FB3FF')
  results.checks.ringLandsOnElement = analyze
  const overlayCount = await runTool('count', overlay.file, '4FB3FF')
  const shotCount = await runTool('count', protectedShot.file, '4FB3FF')
  results.checks.contentProtection = { overlayPngRingPixels: overlayCount.count, groundShotRingPixels: shotCount.count, excluded: overlayCount.count > 500 && shotCount.count < overlayCount.count * 0.02 }
  log('ring', JSON.stringify(analyze))
  log('protection', JSON.stringify(results.checks.contentProtection))
  }

  // ---- click-through ----
  if (!skip.has('click')) {
  const click = spawnLogged(electron, [tool, 'click', tmp])
  const ready = await waitFor(() => click.lines.find((l) => l.includes('"ready":"click"')), 15000, 'click target')
  const centre = JSON.parse(ready.slice(ready.indexOf('{'))).center
  await post('/overlay', { cmd: { type: 'show', annotations: [{ id: 'check-click-ring', kind: 'ring', tone: 'guide', box: { xmin: 170, ymin: 290, xmax: 470, ymax: 570 } }] } })
  await sleep(800)
  let clickError = null
  try {
    execFileSync('swift', [path.join(here, 'click.swift'), String(centre.x), String(centre.y)], { stdio: 'pipe', timeout: 60000 })
  } catch (e) {
    clickError = String(e.stderr ?? e.message).slice(0, 200)
  }
  await sleep(700)
  results.checks.clickThrough = { clickPoint: centre, ringDrawnAbove: true, reachedWindowBelow: click.lines.some((l) => l.includes('CLICKED')), error: clickError }
  log('click-through', JSON.stringify(results.checks.clickThrough))
  click.kill('SIGTERM')
  await post('/overlay', { cmd: { type: 'clear' } })
  await sleep(500)
  }

  // ---- point_at against the real grounder ----
  const pointStart = Date.now()
  const point = await post('/tool', { name: 'point_at', args: { target: process.env.POINT_TARGET ?? 'the grey Settings gear icon in the left sidebar' } })
  results.checks.pointAt = { result: point, ms: Date.now() - pointStart }
  await sleep(1300)
  const pOverlay = await save('/overlay.png', path.join(outDir, 'real-point-at-overlay.png'))
  const pShot = await save('/shot?purpose=ground', path.join(outDir, 'real-point-at-ground-shot.jpg'))
  results.checks.pointAt.composite = await runTool('composite', pShot.file, pOverlay.file, path.join(outDir, 'real-point-at.png'))
  results.checks.pointAt.ring = await runTool('analyze', pOverlay.file, path.join(tmp, 'rects.json'), POINT_ID, '4FB3FF', 'blob')
  log('point_at', JSON.stringify(results.checks.pointAt.result))
  await post('/tool', { name: 'clear_annotations', args: {} })
  await stopApp(app)

  // ---- pass 2: capturable mode + full-screen app ----
  app = await startApp({ ALONGSIDE_OVERLAY_CAPTURABLE: '1' })
  await post('/overlay', { cmd: { type: 'show', annotations: [ring] } })
  await sleep(1200)
  const liveShot = await save('/shot?purpose=live', path.join(outDir, 'real-capturable-live-shot.jpg'))
  const groundShot = await save('/shot?purpose=ground', path.join(outDir, 'real-capturable-ground-shot.jpg'))
  // JPEG + downscale make exact-colour counts unreliable here; the evidence is the pair of images (ring and the
  // level chip present in the live grab, absent in the ground grab).
  results.checks.capturableMode = { liveShot: path.basename(liveShot.file), groundShot: path.basename(groundShot.file), note: 'inspect: overlay visible in live, hidden in ground' }
  log('capturable', JSON.stringify(results.checks.capturableMode))

  const full = spawnLogged(electron, [tool, 'fullscreen'])
  await waitFor(() => full.lines.find((l) => l.includes('"ready":"fullscreen"')), 20000, 'full-screen window')
  await sleep(800)
  const fsShot = await save('/shot?purpose=live', path.join(outDir, 'real-fullscreen-live-shot.jpg'))
  results.checks.aboveFullScreenApp = { fullScreenWindowReported: full.lines.find((l) => l.includes('isFullScreen')) ?? null, shot: path.basename(fsShot.file), note: 'inspect: ring drawn over the cyan full-screen app' }
  log('fullscreen', JSON.stringify(results.checks.aboveFullScreenApp))
  full.kill('SIGTERM')
  stage.kill('SIGTERM')
  await stopApp(app)
} catch (err) {
  results.error = String(err?.stack ?? err)
  log('FAILED', results.error)
} finally {
  fs.writeFileSync(path.join(outDir, 'real-check.json'), JSON.stringify(results, null, 2))
  killAll()
  console.log('[real-check] summary ' + JSON.stringify(results.checks))
  setTimeout(() => process.exit(results.error ? 1 : 0), 500)
}
