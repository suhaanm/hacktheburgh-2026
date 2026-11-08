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
import { createAgentPills } from './agent-pills'
import { createAskBar } from './ask-bar'
import { createKnackShell, type KnackShell } from './knack-shell'
import { createStack } from './stack'
import { realStackDeps } from './stack-real'
import { createHudModel } from '../hud-model'
import { registerHud } from '../hud'
import { SettingsStore } from '../settings'
import { STARTING_URL } from './mainwindow'
import { resolveStackConfig } from './stack-config'

// What the Ask bar shows under the input when a typed task cannot be taken (wake/texts.ts TYPED_LINES.unavailable): the text stays in the box.
const REFUSED_LINE = 'The task service is not answering. Try again soon.'
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
function fakeService(name: string, health: () => unknown, route?: (req: http.IncomingMessage, res: http.ServerResponse) => boolean): Promise<{ server: http.Server; port: number }> {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      const chunks: Buffer[] = []
      req.on('data', (c: Buffer) => chunks.push(c))
      req.on('end', () => {
        seen.push({ name, method: req.method ?? '', url: req.url ?? '', headers: req.headers, body: Buffer.concat(chunks).toString('utf8') })
        if (route?.(req, res)) return
        const send = (v: unknown): void => {
          res.setHeader('content-type', 'application/json')
          res.end(JSON.stringify(v))
        }
        if (req.url === '/health') return send(health())
        if (req.url?.startsWith('/agents/runs')) return send([])
        if (req.method === 'POST') return send({ ok: true, echo: req.url })
        // A route the stand-in does not know is a plain 404, as a service that is up but has not that layer: the dashboard then shows its example data
        // instead of choking on a made-up shape.
        res.statusCode = 404
        send({ error: { code: 'not_found', message: 'not available' } })
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
  // The agent stand-in also serves the task events (an open event stream the check writes to), as the real service does.
  const taskStreams = new Set<http.ServerResponse>()
  const sendTask = (event: string, data: unknown): void => {
    for (const r of taskStreams) r.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
  }
  const agent = await fakeService('agent', () => ({ ok: true, mock: false, supervisor: { state: 'idle', generation: 1 }, data_dir_id: 'check' }), (req, res) => {
    if (req.url !== '/tasks/events') return false
    res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' })
    res.write(`event: snapshot\ndata: ${JSON.stringify({ tasks: [] })}\n\n`)
    taskStreams.add(res)
    res.on('close', () => taskStreams.delete(res))
    return true
  })
  const env: Record<string, string | undefined> = { GEMINI_API_KEY: 'present', UNDERSTUDY_DATA_DIR: dataDir, ENGINE_PORT: String(engine.port), AGENT_PORT: String(agent.port), DASHBOARD_PORT: '9' }

  await app.whenReady()
  const config = { ...resolveStackConfig({ env, appPath: '/nowhere', isPackaged: true, resourcesPath: undefined, exists: (p) => fs.existsSync(p), readFile: (p) => fs.readFileSync(p, 'utf8') }), distDir, devUrl: null, preferDevServer: false }
  const stack = createStack(realStackDeps(config))
  const settings = new SettingsStore(null)
  const calls = { killTriggered: 0, settings: 0, stop: 0, relaunch: 0 }
  const effects: { effect: Effect; event: ShellEvent }[] = []
  let pending = 3
  let suppressed: string | null = null
  const asked: string[] = []
  const ringed: string[] = []
  const revealed: string[] = []
  // A power save blocker that records what is held (the real one would keep this Mac awake while the check runs).
  const held = new Map<number, string>()
  const blocker = { start: (t: string): number => (held.set(held.size + 1000, t), held.size + 999), stop: (id: number): void => void held.delete(id), isStarted: (id: number): boolean => held.has(id) }
  const shell: KnackShell = createKnackShell({
    blocker: blocker as never,
    reveal: (p) => void revealed.push(p),
    settings,
    userDataDir: userData,
    config,
    hidden: true,
    env,
    glyphSvg: glyphFile ? fs.readFileSync(glyphFile, 'utf8') : '',
    bootCheck: async () => true,
    killAccelerator: () => 'CommandOrControl+Alt+Shift+K',
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

  // ---- 2b. the dashboard's Settings switches reach the desktop settings through the page's own bridge, and only the listed ones
  const bridge = (await wc.executeJavaScript(`(async () => {
    const before = await window.knackSettings.getSettings()
    const after = await window.knackSettings.patchSettings({ minimiseWhileWorking: false, useLiveModels: false, fileFolders: ['/'], awaySeconds: 1 })
    const models = await window.knackShell.models.get()
    return { before, after, models }
  })()`)) as { before: Record<string, unknown>; after: Record<string, unknown>; models: Record<string, unknown> }
  check('the page reads the desktop switches and changes the move-aside one, and the other keys it sent are dropped', bridge.before.minimiseWhileWorking === true && bridge.after.minimiseWhileWorking === false && settings.get().moveAsideWhileWorking === false && settings.get().useLiveModels === true && bridge.after.useLiveModels === true && !('fileFolders' in bridge.after), bridge)
  check('the live models switch reports its state to the page and is separate from the settings bridge', typeof bridge.models.useLiveModels === 'boolean' && typeof bridge.models.keyPresent === 'boolean' && typeof bridge.models.running === 'boolean', bridge.models)
  settings.patch({ moveAsideWhileWorking: true })

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
  shell.mainWindow.pushUiState({ kind: 'starting', text: 'Starting Knack…', notice: 'Models are off' })
  await sleep(400)
  const startText = (await wc.executeJavaScript(`document.getElementById('text').textContent + '|' + document.getElementById('notice').textContent + '|' + document.getElementById('retry').hidden`)) as string
  check('the starting page says Starting Knack… and the one calm notice, with no button', startText === 'Starting Knack…|Models are off|true', startText)
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
    kill: { trigger: () => killSwitch.trigger(), clear: () => killSwitch.clear(), isKilled: () => killed, subscribe: (cb) => killSwitch.subscribe(() => cb()) },
    hud: model,
    probe: async () => ({ suppressed, presenting: false }),
    pendingQueue: async () => pending,
    // Stand-ins for what the first run asks macOS: nothing here prompts, and what is asked is recorded.
    permissions: {
      status: async () => ({ microphone: 'not-determined', screen: 'granted', accessibility: false, probe: 'ok', needsRestart: false, hint: '/Applications/Terminal.app secret hint' }),
      requestMicrophone: async () => (asked.push('microphone'), true),
      requestScreen: async () => (asked.push('screen'), { microphone: 'not-determined', screen: 'granted', accessibility: false, probe: 'ok', needsRestart: false, hint: '' }),
      requestAccessibility: () => (asked.push('accessibility'), false),
      openSettings: (pane) => void asked.push(`open:${pane}`),
    },
    speech: { helper: () => ({ state: 'stopped', code: null }), request: () => void asked.push('speech') },
    ring: { show: (box, o) => void ringed.push(`show ${box.join(',')} ghost=${o?.ghost === true}`), clear: () => void ringed.push('clear'), displayBounds: () => screen.getPrimaryDisplay().bounds },
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
  check('the Mac is kept awake for the run (the display too, it uses the real screen)', [...held.values()].join() === 'prevent-display-sleep', [...held.values()])
  shell.dispatch({ type: 'run_progress', label: 'Filling in calculator B', n: 3, m: 8 })
  await settle(900)
  check('the pill shows the words and n of m', model.state().activity?.label === 'Filling in calculator B' && model.state().activity?.step === 3 && model.state().activity?.of === 8, model.state().activity)
  const b1 = hudBounds()
  check('the corner column sits bottom-right of the work area, 16 px in', b1 !== null && Math.abs(b1.x + b1.width - (wa.x + wa.width - 16)) <= 1 && Math.abs(b1.y + b1.height - (wa.y + wa.height - 16)) <= 1, { bounds: b1, workArea: wa })
  check('the pill-only column is small (the window is sized to its content)', b1 !== null && b1.height <= 60 && b1.width <= 340, b1)
  await hudShot('working')
  // One Stop, one square (the owner saw "two stop icons"): the pill's Stop is a single button with a single drawn square and the word, no icon component and no text glyph on top.
  const hudWin = hud.window()
  const stopDom = hudWin ? ((await hudWin.webContents.executeJavaScript(`({ stopButtons: [...document.querySelectorAll('button')].filter((b) => /^\\s*stop\\s*$/i.test(b.textContent || '')).length, squares: document.querySelectorAll('.cbtn.stop .square').length, other: document.querySelectorAll('.cbtn.stop svg, .cbtn.stop .glyph, .cbtn.stop .al-icon, .pill.stop, .al-stop').length, text: (document.querySelector('.cbtn.stop')?.textContent || '').trim(), glyphsInText: /[\\u25A0\\u25FC\\u23F9\\u2B1B]/.test(document.body.textContent || '') })`)) as { stopButtons: number; squares: number; other: number; text: string; glyphsInText: boolean }) : null
  check('the pill has exactly one Stop: one button, one drawn square, the word, and no second icon or text glyph', stopDom?.stopButtons === 1 && stopDom.squares === 1 && stopDom.other === 0 && stopDom.text === 'Stop' && !stopDom.glyphsInText, stopDom)

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
  check('and nothing is held once the run is over', held.size === 0, [...held.values()])
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
  const stoppedDom = hudWin ? ((await hudWin.webContents.executeJavaScript(`({ stopButtons: [...document.querySelectorAll('button')].filter((b) => /^\\s*stop\\s*$/i.test(b.textContent || '')).length, pills: document.querySelectorAll('.cpill').length, buttons: [...document.querySelectorAll('button')].map((b) => (b.textContent || '').trim()) })`)) as { stopButtons: number; pills: number; buttons: string[] }) : null
  check('while everything is stopped there is no Stop to press: the Stopped card has Resume and the pill is gone', stoppedDom?.stopButtons === 0 && stoppedDom.pills === 0 && stoppedDom.buttons.some((b) => /resume/i.test(b)), stoppedDom)
  await killSwitch.clear()
  await settle(300)
  check('Resume leaves the stopped state', shell.info().machine.activity === 'idle' && model.state().kill.killed === false, shell.info().machine)

  // ---- 5b. the first run's bridge: what it sees of macOS (closed words only), what it may ask, who may ask, and the sample ring
  const perm = (await wc.executeJavaScript(`(async () => {
    const p = window.knackShell.permissions
    return {
      state: await p.state(),
      badKind: await p.request('camera'),
      screen: await p.request('screen'),
      speech: await p.request('speech'),
      mic: await p.request('microphone'),
      open: await p.openSettings('accessibility'),
      badOpen: await p.openSettings('../etc'),
      ring: await window.knackShell.tryRing(),
      badRing: await window.knackShell.tryRing({ x: 'a' }),
    }
  })()`)) as { state: Record<string, unknown>; badKind: { ok: boolean; reason?: string }; screen: { ok: boolean }; speech: { ok: boolean }; mic: { ok: boolean }; open: boolean; badOpen: boolean; ring: { ok: boolean; reason?: string }; badRing: { ok: boolean; reason?: string } }
  check('the first run reads macOS as closed words only: four kinds and one restart flag, nothing else', JSON.stringify(Object.keys(perm.state).sort()) === JSON.stringify(['accessibility', 'microphone', 'needsRestart', 'screen', 'speech']) && perm.state.microphone === 'not_asked' && perm.state.screen === 'granted' && !JSON.stringify(perm.state).includes('Terminal'), perm.state)
  check('it can ask for the four kinds by name, and a name it does not know asks nothing', perm.badKind.ok === false && perm.badKind.reason === 'bad_request' && perm.screen.ok && perm.speech.ok && perm.mic.ok && asked.filter((a) => !a.startsWith('open:')).join() === 'screen,speech,microphone', [...asked])
  check('it can open the System Settings pane for a kind, and not for anything else', perm.open === true && perm.badOpen === false && asked.at(-1) === 'open:accessibility', [...asked])
  check('the sample ring needs the window in view: while it is hidden it says so and draws nothing, and a bad spot is refused', perm.ring.ok === false && perm.ring.reason === 'window_hidden' && ringed.length === 0 && perm.badRing.ok === false, { ring: perm.ring, badRing: perm.badRing, ringed })
  // Only the Knack window's own page may ask: another window of the app, with the same preload, is refused.
  const stranger = new BrowserWindow({ show: false, webPreferences: { preload: path.join(__dirname, '../preload/knack.js'), sandbox: true, contextIsolation: true } })
  await stranger.loadURL('about:blank')
  const refused = (await stranger.webContents.executeJavaScript(`Promise.all([window.knackShell.permissions.state(), window.knackShell.tryRing(), window.knackSettings.getSettings()].map((p) => p.then(() => 'answered', () => 'refused')))`)) as string[]
  stranger.destroy()
  check('another window of the app is refused by the permission, ring and settings calls', refused.join() === 'refused,refused,refused', refused)
  asked.length = 0

  // ---- 5c. the Ask bar: a small centred input that sends a line and says one plain sentence when it cannot be answered
  let askClosed = 0
  const submitted: string[] = []
  const ask = createAskBar({
    hidden: true,
    disabled: false,
    capturable: false,
    onClosed: () => void (askClosed += 1),
    submit: (text) => {
      submitted.push(text)
      return text.startsWith('inject') ? { ok: true } : { ok: false, line: REFUSED_LINE }
    },
  })
  ask.open('hello there')
  const askWin = await waitFor(() => (ask.window()?.webContents.isLoading() === false ? ask.window() : null), 10000)
  await settle(500)
  const askPage = askWin ? ((await askWin.webContents.executeJavaScript(`({ value: document.getElementById('input').value, placeholder: document.getElementById('input').placeholder, replyHidden: document.getElementById('reply').hidden, knackAsk: typeof window.knackAsk, title: document.title })`)) as { value: string; placeholder: string; replyHidden: boolean; knackAsk: string; title: string }) : null
  check('the Ask bar opens with the phrase it was given, an empty answer line and its own four calls', askPage?.value === 'hello there' && askPage.placeholder === 'Ask Knack' && askPage.replyHidden && askPage.knackAsk === 'object' && ask.isOpen(), askPage)
  const askBounds = askWin?.getBounds()
  check('the Ask bar is centred across the work area, 560 wide with room for its shadow, in the upper third', askBounds !== undefined && Math.abs(askBounds.x + askBounds.width / 2 - (wa.x + wa.width / 2)) <= 1 && askBounds.width === 576 && askBounds.y + 8 < wa.y + wa.height / 3, { askBounds, wa })
  const askShot = async (name: string): Promise<void> => {
    for (const theme of ['light', 'dark'] as const) {
      nativeTheme.themeSource = theme
      await sleep(350)
      const png = await ask.png()
      if (png) fs.writeFileSync(path.join(out, `ask-${name}-${theme}.png`), png)
    }
    nativeTheme.themeSource = 'system'
  }
  await askShot('open')
  const sent = (await askWin?.webContents.executeJavaScript(`(async () => { const r = await window.knackAsk.submit('where is the calculator'); return r })()`)) as { ok: boolean; line?: string } | undefined
  await settle(400)
  check('a line that cannot be answered stays open with one plain sentence (nothing is lost, nothing pretends to work)', sent?.ok === false && sent.line === REFUSED_LINE && ask.isOpen() && submitted.at(-1) === 'where is the calculator', { sent, submitted })
  await askWin?.webContents.executeJavaScript(`document.getElementById('input').value = 'where is the calculator'; document.getElementById('card').requestSubmit()`)
  await settle(600)
  const askReply = (await askWin?.webContents.executeJavaScript(`({ hidden: document.getElementById('reply').hidden, text: document.getElementById('reply').textContent })`)) as { hidden: boolean; text: string } | undefined
  check('the page shows that sentence under the input, and the window grows to fit it', askReply?.hidden === false && askReply.text === REFUSED_LINE && (ask.window()?.getBounds().height ?? 0) > 80, { askReply, height: ask.window()?.getBounds().height })
  await askShot('reply')
  const accepted = (await askWin?.webContents.executeJavaScript(`window.knackAsk.submit('  inject   this\\nline ')`)) as { ok: boolean } | undefined
  check('a line that is taken closes the bar, cleaned to one line', accepted?.ok === true && !ask.isOpen() && submitted.at(-1) === 'inject this line' && askClosed === 1, { accepted, submitted, askClosed })
  ask.open()
  await settle(300)
  await askWin?.webContents.executeJavaScript(`window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))`)
  await settle(300)
  check('Escape closes it, and it opens again empty', !ask.isOpen() && askClosed === 2, { askClosed })
  ask.open()
  await settle(300)
  const strangerAsk = new BrowserWindow({ show: false, webPreferences: { preload: path.join(__dirname, '../preload/ask.js'), sandbox: true, contextIsolation: true } })
  await strangerAsk.loadURL('about:blank')
  const foreign = (await strangerAsk.webContents.executeJavaScript(`window.knackAsk.submit('from a stranger').then(() => 'answered', () => 'refused')`)) as string
  strangerAsk.destroy()
  check("only the bar's own page can send a line: another window is refused and nothing is submitted", foreign === 'refused' && !submitted.includes('from a stranger'), { foreign, submitted })
  ask.dispose()

  // ---- 5d. the background agent pills (top right): one pill per task the service says is going on, from its event stream; a quiet check that fades; a failure that stays
  const opened: { id: string; phase: string }[] = []
  const pills = createAgentPills({ source: shell.agentRuns, onOpen: (i) => void opened.push({ id: i.id, phase: i.phase }), onStop: (id) => void shell.stopWork(id), hidden: true, disabled: false, capturable: false })
  const row = (id: string, state: string, over: Record<string, unknown> = {}) => ({ task_id: id, title: 'Fill in the quarterly benefits form', route: 'browser', state, source: 'typed', attended: false, latest: null, steps_done: 0, result: null, reason: null, started: new Date().toISOString(), finished: null, open: null, needs_consent: null, question: null, ...over })
  await waitFor(() => (taskStreams.size > 0 ? true : null), 8000) // the shell has opened the stream
  sendTask('task_started', row('tk_aaaa1111', 'running', { latest: 'Opening the leave page for the claim' }))
  sendTask('task_started', row('tk_bbbb2222', 'waiting_consent', { route: 'desktop', title: 'Send the weekly summary' }))
  sendTask('task_started', row('tk_cccc3333', 'planning', { route: 'answer', title: 'Work out the overlap' }))
  const pillsWin = await waitFor(() => (pills.window()?.webContents.isLoading() === false && pills.view().items.length === 3 ? pills.window() : null), 10000)
  await settle(700)
  type PillDom = { count: number; texts: string[]; phases: string[]; animated: string[]; rings: number; dots: number; stops: number; moreText: string | null }
  const readPills = async (): Promise<PillDom | null> =>
    pillsWin
      ? ((await pillsWin.webContents.executeJavaScript(`(() => { const ps = [...document.querySelectorAll('.pill:not(.more)')]; const more = document.querySelector('.pill.more'); return { count: ps.length, texts: ps.map((p) => p.querySelector('.text')?.textContent), phases: ps.map((p) => p.dataset.phase), animated: ps.map((p) => p.querySelector('.icon')?.dataset.animated), rings: document.querySelectorAll('.ring').length, dots: document.querySelectorAll('.icon .dot').length, stops: document.querySelectorAll('.stop').length, moreText: more ? more.textContent : null } })()`)) as PillDom)
      : null
  const p1 = await readPills()
  check('a task the service says is running, one that waits for an OK and one that is planning each get a pill, with four words at most and the step line before the title', p1?.count === 3 && p1.texts[0] === 'Opening the leave page…' && p1.texts[1] === 'Send the weekly summary' && p1.phases.join() === 'working,waiting,working', p1)
  check('only the running task moves its icon; the waiting one is still with a dot; each can be stopped', p1?.animated.join() === 'true,false,false' && p1.dots === 1 && p1.stops === 3, p1)
  const pb = pills.window()?.getBounds()
  check('the pills sit at the top right: 16 px in from the right edge, 16 px below the top of the work area (under the menu bar)', pb !== undefined && Math.abs(pb.x + pb.width - 3 - (wa.x + wa.width - 16)) <= 1 && Math.abs(pb.y + 3 - (wa.y + 16)) <= 1 && pb.y >= wa.y, { pb, wa })
  const pillShot = async (name: string): Promise<void> => {
    for (const theme of ['light', 'dark'] as const) {
      nativeTheme.themeSource = theme
      await sleep(350)
      const png = await pills.png()
      if (png) fs.writeFileSync(path.join(out, `pills-${name}-${theme}.png`), png)
    }
    nativeTheme.themeSource = 'system'
  }
  await pillShot('working')
  await pillsWin?.webContents.executeJavaScript(`document.querySelectorAll('.pill .open')[1].click()`)
  await pillsWin?.webContents.executeJavaScript(`document.querySelectorAll('.pill .open')[0].click()`)
  await pillsWin?.webContents.executeJavaScript(`document.querySelectorAll('.pill .stop')[0].click()`)
  await settle(500)
  const stopSeen = seen.find((x) => x.name === 'agent' && x.method === 'POST' && x.url === '/tasks/tk_aaaa1111/stop')
  check('a click opens Knack on that work (Needs you for the one waiting, Routines for the other), and the stop button reaches the service as the worker', opened.map((o) => `${o.id}:${o.phase}`).join() === 'tk_bbbb2222:waiting,tk_aaaa1111:working' && stopSeen?.headers['x-understudy-actor'] === 'worker' && stopSeen.body === '{}', { opened, stopSeen: stopSeen?.headers })
  sendTask('task_finished', row('tk_cccc3333', 'done', { result: 'The overlap is 12 days', finished: new Date().toISOString(), open: { kind: 'folder', path: '/tmp/knack-check-result' } }))
  sendTask('task_finished', row('tk_bbbb2222', 'failed', { reason: 'Mail did not answer', finished: new Date().toISOString() }))
  await settle(900)
  const p2 = await readPills()
  check('a finished task shows a quiet check with its one result line, and a failure shows a red dot with its reason', p2?.phases.join() === 'working,failed,done' && p2.texts[2] === 'The overlap is 12 days' && p2.texts[1] === 'Mail did not answer', p2)
  const reveal = (await wc.executeJavaScript(`Promise.all([window.knackShell.reveal('/tmp/knack-check-result'), window.knackShell.reveal('/etc/passwd'), window.knackShell.reveal('/tmp/knack-check-result/../../etc'), window.knackShell.reveal(7)])`)) as boolean[]
  check('the page can reveal only a path the service recorded for a task: the recorded one is shown, any other string is refused', reveal.join() === 'true,false,false,false' && revealed.join() === '/tmp/knack-check-result', { reveal, revealed })
  await pillShot('ended')
  await sleep(5600)
  const p3 = await readPills()
  check('the check fades by itself after five seconds and leaves nothing behind, while the failure stays until it is clicked', p3?.phases.join() === 'working,failed' && p3.count === 2, p3)
  sendTask('task_finished', row('tk_aaaa1111', 'stopped', { finished: new Date().toISOString() }))
  await settle(600)
  await pillsWin?.webContents.executeJavaScript(`document.querySelectorAll('.pill[data-phase="failed"] .open')[0].click()`)
  await sleep(900)
  const p4 = await readPills()
  check('clicking the failure opens Knack on it and takes the red dot away; a stopped task shows a dash and goes by itself', (p4?.count ?? 9) <= 1 && opened.at(-1)?.phase === 'failed', { p4, opened })
  await sleep(3600)
  check('and when the service has nothing going on, no pill is left (the pill list is exactly the work that is not finished)', (await readPills())?.count === 0 && pills.view().items.length === 0, pills.view())
  // A new task on the same stream shows up again at once.
  const outageCheck = await (async () => {
    sendTask('task_started', row('tk_dddd4444', 'running', { title: 'Check the bank holidays' }))
    await waitFor(() => (pills.view().items.length === 1 ? true : null), 5000)
    return pills.view().items.map((i) => `${i.phase}:${i.text}`)
  })()
  check('a new task shows up again at once on the same stream', outageCheck.join() === 'working:Check the bank holidays', outageCheck)
  pills.dispose()

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
