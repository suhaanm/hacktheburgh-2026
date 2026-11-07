// The hidden check of the Knack shell (run by scripts/knack-check.mjs; never part of the app). A separate Electron main that builds the real shell and the real HUD
// corner column with stand-in services on private ports and a private data directory: every window is created and works but is NEVER shown, there is no Dock icon and no
// menu bar (activation policy "prohibited"), nothing is read from or sent to the desktop, and no real input is made. It checks the dashboard served from app://knack, the
// token-adding proxy, the corner column (where it sits, what the machine puts in it, which card wins, what waits), and writes a picture of each page (the page's own
// pixels, not the screen) so they can be looked at.
import fs from 'node:fs'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import { app, BrowserWindow, nativeTheme, screen } from 'electron'
import { registerAppScheme } from './app-protocol-electron'
import { createKnackShell, type KnackShell } from './knack-shell'
import { createStack } from './stack'
import { realStackDeps } from './stack-real'
import { createHudModel } from '../hud-model'
import { registerHud } from '../hud'
import { SettingsStore } from '../settings'
import { STARTING_URL } from './mainwindow'
import { resolveStackConfig } from './stack-config'
import type { Effect, ShellEvent } from './shell-machine'

if (process.platform === 'darwin') {
  app.setActivationPolicy('prohibited') // no Dock icon, no menu bar, and nothing can be shown
  app.dock?.hide()
}
registerAppScheme()

const out = process.env.KNACK_CHECK_OUT ?? fs.mkdtempSync(path.join(os.tmpdir(), 'knack-check-'))
const distDir = process.env.KNACK_CHECK_DIST ?? ''
const glyphFile = process.env.KNACK_CHECK_GLYPH ?? ''
const results: { name: string; ok: boolean; detail?: unknown }[] = []
const check = (name: string, ok: boolean, detail?: unknown): void => {
  results.push({ name, ok: Boolean(ok), detail })
}
const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))
const waitFor = async <T>(fn: () => Promise<T | null | false | undefined> | T | null | false | undefined, ms: number): Promise<T | null> => {
  const end = Date.now() + ms
  while (Date.now() < end) {
    const v = await fn()
    if (v) return v as T
    await sleep(100)
  }
  return null
}

interface Seen {
  name: string
  method: string
  url: string
  headers: http.IncomingHttpHeaders
  body: string
}
const seen: Seen[] = []
function fakeService(name: string, health: () => unknown): Promise<{ server: http.Server; port: number }> {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      const chunks: Buffer[] = []
      req.on('data', (c: Buffer) => chunks.push(c))
      req.on('end', () => {
        seen.push({ name, method: req.method ?? '', url: req.url ?? '', headers: req.headers, body: Buffer.concat(chunks).toString('utf8') })
        const send = (v: unknown): void => {
          res.setHeader('content-type', 'application/json')
          res.end(JSON.stringify(v))
        }
        if (req.url === '/health') return send(health())
        if (req.url?.startsWith('/agents/runs')) return send([])
        send({ ok: true, echo: req.url })
      })
    })
    server.listen(0, '127.0.0.1', () => resolve({ server, port: (server.address() as { port: number }).port }))
  })
}

async function run(): Promise<void> {
  fs.mkdirSync(out, { recursive: true })
  const work = fs.mkdtempSync(path.join(os.tmpdir(), 'knack-check-data-'))
  const dataDir = path.join(work, 'data')
  fs.mkdirSync(dataDir, { recursive: true })
  const TOKEN = 'check-token-0123456789abcdef'
  fs.writeFileSync(path.join(dataDir, '.token'), TOKEN)
  const userData = path.join(work, 'userData')
  app.setPath('userData', userData)

  const engine = await fakeService('engine', () => ({ ok: true, mock: false }))
  const agent = await fakeService('agent', () => ({ ok: true, mock: false, supervisor: { state: 'idle', generation: 1 }, data_dir_id: 'check' }))
  const env: Record<string, string | undefined> = { GEMINI_API_KEY: 'present', UNDERSTUDY_DATA_DIR: dataDir, ENGINE_PORT: String(engine.port), AGENT_PORT: String(agent.port), DASHBOARD_PORT: '9' }

  await app.whenReady()
  const config = { ...resolveStackConfig({ env, appPath: '/nowhere', isPackaged: true, resourcesPath: undefined, exists: (p) => fs.existsSync(p), readFile: (p) => fs.readFileSync(p, 'utf8') }), distDir, devUrl: null, preferDevServer: false }
  const stack = createStack(realStackDeps(config))
  const settings = new SettingsStore(null)
  const calls = { killTriggered: 0, settings: 0, stop: 0, relaunch: 0 }
  const effects: { effect: Effect; event: ShellEvent }[] = []
  let pending = 3
  let suppressed: string | null = null
  const shell: KnackShell = createKnackShell({
    settings,
    userDataDir: userData,
    config,
    hidden: true,
    env,
    glyphSvg: glyphFile ? fs.readFileSync(glyphFile, 'utf8') : '',
    bootCheck: async () => true,
    killAccelerator: () => 'CommandOrControl+Alt+Shift+K',
    openSettings: () => void (calls.settings += 1),
    stopEverything: () => void (calls.stop += 1),
    relaunch: () => void (calls.relaunch += 1),
    showSheet: async () => 'keep_working',
    stack,
    log: () => undefined,
    onEffect: (effect, event) => effects.push({ effect, event }),
  })

  // ---- 1. the models are chosen, the stack attaches to the stand-in services, the window leaves the starting page for the dashboard
  const decision = await shell.planned
  check('live models chosen when a key is present and the check passes', decision.mode === 'live' && decision.notice === null, decision)
  const ready = await waitFor(() => (stack.state().phase === 'ready' ? stack.state() : null), 8000)
  check('the stack attaches to the running services and starts nothing', ready !== null && stack.started().length === 0, ready)
  check('the status is live', shell.modelStatus().live === true, shell.modelStatus())

  const bw = BrowserWindow.getAllWindows()[0]! // the main window is the only one so far (the HUD is built below)
  const wc = bw.webContents
  const consoleErrors: string[] = []
  wc.on('console-message', (...args: unknown[]) => {
    const e = args[0] as { level?: string | number; message?: string }
    const level = typeof e === 'object' && e !== null ? e.level : args[1]
    const message = (typeof e === 'object' && e !== null ? e.message : args[2]) as string
    if (/Content Security Policy|Refused to/i.test(String(message)) || level === 'error' || level === 3) consoleErrors.push(String(message).slice(0, 200))
  })
  const dash = await waitFor(() => (wc.getURL().startsWith('app://knack/') && !wc.getURL().includes('__shell') && !wc.isLoading() ? wc.getURL() : null), 15000)
  check('the window loads the dashboard from app://knack/', (dash ?? '').startsWith('app://knack/'), dash)
  const wa = screen.getPrimaryDisplay().workArea
  const b0 = bw.getBounds()
  check('the window opened at the spec size on this display: 80 by 84 percent of the work area, clamped to 960..1440 by 600..1000', Math.abs(b0.width - Math.min(wa.width, Math.min(1440, Math.max(960, Math.round(wa.width * 0.8))))) <= 2 && Math.abs(b0.height - Math.min(wa.height, Math.min(1000, Math.max(600, Math.round(wa.height * 0.84))))) <= 2, { bounds: b0, workArea: wa })
  await waitFor(() => wc.executeJavaScript(`document.getElementById('root')?.children.length > 0`), 15000)
  await sleep(1500)

  const page = (await wc.executeJavaScript(`({
    title: document.title,
    shellAttr: document.documentElement.dataset.knackShell ?? null,
    knackShell: typeof window.knackShell,
    platform: window.knackShell?.platform ?? null,
    width: innerWidth, height: innerHeight,
  })`)) as Record<string, unknown>
  check('the dashboard rendered something', typeof page.title === 'string', page)
  check('the preload gives the page the platform, and the shell marks the inset title bar on the page (macOS)', page.knackShell === 'object' && (process.platform !== 'darwin' || page.shellAttr === 'mac-inset'), { platform: page.platform, shellAttr: page.shellAttr })
  check('no content security policy violation and no console error while it loaded', consoleErrors.length === 0, consoleErrors.slice(0, 5))

  // ---- 2. the proxy adds the token, and only the proxy: the page never sees it
  const viaPage = (await wc.executeJavaScript(`fetch('/engine/health').then(async (r) => ({ status: r.status, body: await r.json(), hasTokenHeader: r.headers.has('x-understudy-token') }))`)) as { status: number; body: { ok?: boolean }; hasTokenHeader: boolean }
  check('the page reads the engine through /engine, and the token never comes back to it', viaPage.status === 200 && viaPage.body.ok === true && viaPage.hasTokenHeader === false, viaPage)
  const eng = seen.filter((s) => s.name === 'engine' && s.url === '/health').at(-1)
  check('the engine received the real token, its own Host, and no Origin on a read', eng?.headers['x-understudy-token'] === TOKEN && eng?.headers.host === `127.0.0.1:${engine.port}` && eng?.headers.origin === undefined)
  const write = (await wc.executeJavaScript(`fetch('/agent/agents/spawn', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Understudy-Actor': 'worker', 'x-understudy-token': 'forged' }, body: JSON.stringify({ kind: 'shadow' }) }).then((r) => r.status)`)) as number
  const spawnReq = seen.filter((s) => s.name === 'agent' && s.url === '/agents/spawn').at(-1)
  check('a write reaches the agent with the dashboard Origin, the JSON body, and a forged token replaced by the real one', write === 200 && spawnReq?.headers.origin === `http://127.0.0.1:${config.ports.dashboard}` && spawnReq?.headers['x-understudy-token'] === TOKEN && spawnReq?.body === '{"kind":"shadow"}')

  // ---- 3. pictures of the dashboard, light and dark, at the window's own size
  for (const theme of ['light', 'dark'] as const) {
    nativeTheme.themeSource = theme
    await sleep(500)
    fs.writeFileSync(path.join(out, `dashboard-${theme}.png`), (await wc.capturePage()).toPNG())
  }
  nativeTheme.themeSource = 'system'

  // ---- 4. the starting page and the error page (pictures)
  shell.mainWindow.loadStarting()
  await waitFor(() => (wc.getURL() === STARTING_URL && !wc.isLoading() ? true : null), 8000)
  shell.mainWindow.pushUiState({ kind: 'starting', text: 'Starting Knack…', notice: 'Running with example data' })
  await sleep(400)
  const startText = (await wc.executeJavaScript(`document.getElementById('text').textContent + '|' + document.getElementById('notice').textContent + '|' + document.getElementById('retry').hidden`)) as string
  check('the starting page says Starting Knack… and the one calm notice, with no button', startText === 'Starting Knack…|Running with example data|true', startText)
  for (const theme of ['light', 'dark'] as const) {
    nativeTheme.themeSource = theme
    await sleep(400)
    fs.writeFileSync(path.join(out, `starting-${theme}.png`), (await wc.capturePage()).toPNG())
  }
  nativeTheme.themeSource = 'system'
  shell.mainWindow.pushUiState({ kind: 'error', message: 'The engine did not start.', hint: 'See data/logs/knack-engine.log.' })
  await sleep(400)
  const errText = (await wc.executeJavaScript(`document.getElementById('text').textContent + '|' + document.getElementById('hint').textContent + '|' + document.getElementById('retry').hidden`)) as string
  check('the error page says one plain sentence, a hint and one Try again button', errText === 'The engine did not start.|See data/logs/knack-engine.log.|false', errText)
  fs.writeFileSync(path.join(out, 'error-light.png'), (await wc.capturePage()).toPNG())

  // ---- 5. the corner column: the real HUD model and window, driven through the machine
  let killed = false
  type K = { killed: boolean; at: null; source: null; engine: null; agent: null }
  const killListeners = new Set<(s: K) => void>()
  const kstate = (): K => ({ killed, at: null, source: null, engine: null, agent: null })
  const killSwitch = {
    trigger: async () => {
      calls.killTriggered += 1
      killed = true
      killListeners.forEach((l) => l(kstate()))
      return { source: 'hud' as const, at: 1, localMs: 1, engine: true, agent: true }
    },
    clear: async () => {
      killed = false
      killListeners.forEach((l) => l(kstate()))
    },
    state: kstate,
    subscribe: (cb: (s: K) => void) => (killListeners.add(cb), () => killListeners.delete(cb)),
  }
  const model = createHudModel({ kill: killSwitch, endpoints: { dashboard: `http://127.0.0.1:${config.ports.dashboard}` }, openExternal: () => undefined, onProposalChoice: () => undefined, push: () => hud.push(), corner: true })
  const hud = registerHud({ model, log: () => undefined, corner: true, hidden: true })
  shell.attach({
    kill: { trigger: () => killSwitch.trigger(), isKilled: () => killed, subscribe: (cb) => killSwitch.subscribe(() => cb()) },
    hud: model,
    probe: async () => ({ suppressed, presenting: false }),
    pendingQueue: async () => pending,
  })
  void pending
  const settle = async (ms = 700): Promise<void> => void (await sleep(ms))
  const hudBounds = () => hud.window()?.getBounds() ?? null
  const hudShot = async (name: string): Promise<void> => {
    for (const theme of ['light', 'dark'] as const) {
      nativeTheme.themeSource = theme
      await sleep(350)
      const png = await hud.png()
      if (png) fs.writeFileSync(path.join(out, `corner-${name}-${theme}.png`), png)
    }
    nativeTheme.themeSource = 'system'
  }
  const types = (): string[] => effects.map((e) => e.effect.type)

  await settle(900)
  check('nothing is in the corner while idle', model.state().activity === null && hud.window() !== null)

  shell.dispatch({ type: 'window_state', window: 'open', focused: true })
  shell.dispatch({ type: 'run_started', realScreen: true })
  check('a run that uses the real screen, with the window focused: the machine asks to minimise it after 400 ms, and the pill says Starting', effects.some((e) => e.effect.type === 'minimizeMainAfter' && (e.effect as { ms: number }).ms === 400) && model.state().activity?.label === 'Starting' && model.state().activity?.phase === 'working', model.state().activity)
  shell.dispatch({ type: 'run_progress', label: 'Filling in calculator B', n: 3, m: 8 })
  await settle(900)
  check('the pill shows the words and n of m', model.state().activity?.label === 'Filling in calculator B' && model.state().activity?.step === 3 && model.state().activity?.of === 8, model.state().activity)
  const b1 = hudBounds()
  check('the corner column sits bottom-right of the work area, 16 px in', b1 !== null && Math.abs(b1.x + b1.width - (wa.x + wa.width - 16)) <= 1 && Math.abs(b1.y + b1.height - (wa.y + wa.height - 16)) <= 1, { bounds: b1, workArea: wa })
  check('the pill-only column is small (the window is sized to its content)', b1 !== null && b1.height <= 60 && b1.width <= 340, b1)
  await hudShot('working')

  shell.dispatch({ type: 'decision_needed', class: 'approval' })
  await settle(900)
  check('a blocked run raises one card above the pill, and never restores the window', model.state().approval !== null && model.state().activity !== null && !types().some((t) => ['openMain', 'restoreMain', 'focusMain', 'openOrRestoreMain'].includes(t)), { approval: model.state().approval })
  const b2 = hudBounds()
  check('the card grows the column upwards, the pill keeps its place', b2 !== null && b1 !== null && b2.height > b1.height && Math.abs(b2.y + b2.height - (b1.y + b1.height)) <= 1, { b1, b2 })
  await hudShot('card')

  suppressed = 'secure_input'
  await sleep(2600)
  check('a password field with focus holds the card (the pill still shows)', model.state().hold.secure === true && model.state().activity !== null, model.state().hold)
  suppressed = null
  await sleep(2600)
  check('and the card comes back when the field loses focus', model.state().hold.secure === false)

  effects.length = 0
  model.handle({ type: 'review', id: model.state().approval!.id })
  await settle(200)
  check('Review opens Knack on Needs you and closes the card', effects.some((e) => e.effect.type === 'openOrRestoreMain') && model.state().approval === null, types())

  shell.dispatch({ type: 'run_done', needsNothing: true })
  await settle(400)
  check('a finished run turns the pill into a check, and the window does not pop back', model.state().activity?.phase === 'done' && !types().some((t) => ['openMain', 'restoreMain', 'focusMain'].includes(t)), model.state().activity)
  await hudShot('done')
  await sleep(3200)
  check('the check fades and the corner window goes by itself', model.state().activity === null, model.state().activity)

  shell.dispatch({ type: 'run_started', realScreen: false })
  shell.dispatch({ type: 'run_failed' })
  await settle(500)
  check('a failed run turns the pill to the error state and holds it', model.state().activity?.phase === 'error', model.state().activity)
  await hudShot('error')
  model.handle({ type: 'pill_open' })
  await settle(200)
  check('Open on the error pill opens Knack and clears the pill', model.state().activity === null, model.state().activity)

  shell.dispatch({ type: 'run_started', realScreen: false })
  shell.dispatch({ type: 'voice_hold', phase: 'Listening' })
  await settle(500)
  check('voice uses the same pill (End instead of Stop)', model.state().activity?.phase === 'voice' && model.state().activity?.label === 'Listening', model.state().activity)
  await hudShot('voice')
  model.handle({ type: 'voice_end' })
  shell.dispatch({ type: 'run_started', realScreen: false })
  await killSwitch.trigger()
  await settle(600)
  check('kill wins: the Stopped card replaces the pill, and the machine is stopped', model.state().kill.killed === true && model.state().activity === null && shell.info().machine.activity === 'stopped', shell.info().machine)
  shell.dispatch({ type: 'run_started', realScreen: false })
  check('a run that starts while stopped is ignored', model.state().activity === null)
  await hudShot('stopped')
  await killSwitch.clear()
  await settle(300)
  check('Resume leaves the stopped state', shell.info().machine.activity === 'idle' && model.state().kill.killed === false, shell.info().machine)

  // ---- 6. close, activate, the setting
  shell.dispatch({ type: 'window_close' })
  check('closing the window hides it and stops nothing', shell.info().machine.window === 'absent')
  effects.length = 0
  shell.dispatch({ type: 'dock_click_or_activate' })
  check('the Dock icon from closed opens the window again', effects.some((e) => e.effect.type === 'openMain'))

  settings.patch({ useLiveModels: false }, { trusted: true })
  await sleep(100)
  check('switching Use live models off restarts the app (relaunch is called once)', calls.relaunch === 1, calls)

  const failed = results.filter((r) => !r.ok)
  fs.writeFileSync(path.join(out, 'knack-check.json'), JSON.stringify({ results, failed: failed.length }, null, 2))
  for (const r of results) console.log(`${r.ok ? 'PASS' : 'FAIL'} ${r.name}${r.ok ? '' : ` ${JSON.stringify(r.detail)}`}`)
  console.log(`${results.length - failed.length}/${results.length} passed; pictures in ${out}`)
  engine.server.close()
  agent.server.close()
  await stack.stop()
  app.exit(failed.length === 0 ? 0 : 1)
}

run().catch((err: unknown) => {
  console.log(`CHECK CRASHED ${err instanceof Error ? err.stack : String(err)}`)
  app.exit(2)
})
