// The hidden check of the Knack shell (run by scripts/knack-check.mjs; never part of the app). A separate Electron main that builds the real shell with
// stand-in services on private ports and a private data directory: every window is created and works but is NEVER shown, there is no Dock icon and no menu
// bar (activation policy "prohibited"), nothing is read from or sent to the desktop, and no real input is made. It checks the dashboard served from app://knack,
// the token-adding proxy, the pill states, where the pill sits, click-through and its safety rules, and writes a picture of each page (the page's own pixels, not
// the screen) so they can be looked at.
import fs from 'node:fs'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import { app, BrowserWindow, nativeTheme } from 'electron'
import { registerAppScheme } from './app-protocol-electron'
import { createKnackShell, type KnackShell } from './knack-shell'
import { createStack } from './stack'
import { realStackDeps } from './stack-real'
import { SettingsStore } from '../settings'
import { STARTING_URL } from './main-window'
import { resolveStackConfig } from './stack-config'

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

  let supervisor = 'idle'
  const engine = await fakeService('engine', () => ({ ok: true, mock: false }))
  const agent = await fakeService('agent', () => ({ ok: true, mock: false, supervisor: { state: supervisor, generation: 1 }, data_dir_id: 'check' }))
  const env: Record<string, string | undefined> = { GEMINI_API_KEY: 'present', UNDERSTUDY_DATA_DIR: dataDir, ENGINE_PORT: String(engine.port), AGENT_PORT: String(agent.port), DASHBOARD_PORT: '9' }

  await app.whenReady()
  const config = { ...resolveStackConfig({ env, appPath: '/nowhere', isPackaged: true, resourcesPath: undefined, exists: (p) => fs.existsSync(p), readFile: (p) => fs.readFileSync(p, 'utf8') }), distDir, devUrl: null, preferDevServer: false }
  const stack = createStack(realStackDeps(config))
  const settings = new SettingsStore(null)
  const calls = { killTriggered: 0, settings: 0, stop: 0, relaunch: 0 }
  const actions: { action: string; event: string }[] = []
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
    stack,
    log: () => undefined,
    onAction: (e) => actions.push(e),
  })

  // ---- 1. the models are chosen, the stack attaches to the stand-in services, the window leaves the starting page for the dashboard
  const decision = await shell.planned
  check('live models chosen when a key is present and the check passes', decision.mode === 'live' && decision.notice === null, decision)
  const ready = await waitFor(() => (stack.state().phase === 'ready' ? stack.state() : null), 8000)
  check('the stack attaches to the running services and starts nothing', ready !== null && stack.started().length === 0, ready)
  check('the status is live', shell.modelStatus().live === true, shell.modelStatus())

  const win = shell.mainWindow.window()!
  const wc = win.webContents
  const consoleErrors: string[] = []
  wc.on('console-message', (...args: unknown[]) => {
    const e = args[0] as { level?: string | number; message?: string }
    const level = typeof e === 'object' && e !== null ? e.level : args[1]
    const message = (typeof e === 'object' && e !== null ? e.message : args[2]) as string
    if (/Content Security Policy|Refused to/i.test(String(message))) consoleErrors.push(String(message).slice(0, 200))
    else if (level === 'error' || level === 3) consoleErrors.push(String(message).slice(0, 200))
  })
  const dash = await waitFor(() => (wc.getURL().startsWith('app://knack/') && !wc.getURL().includes('__shell') && !wc.isLoading() ? wc.getURL() : null), 15000)
  check('the window loads the dashboard from app://knack/', dash === 'app://knack/' || (dash ?? '').startsWith('app://knack/'), dash)
  const rendered = await waitFor(() => wc.executeJavaScript(`!!document.querySelector('.wordmark')`), 15000)
  check('the dashboard rendered', rendered === true)
  await sleep(1500) // let the first screen settle (its own requests go through the proxy)

  const page = (await wc.executeJavaScript(`({
    title: document.title,
    wordmark: document.querySelector('.wordmark')?.textContent?.trim(),
    glyph: !!document.querySelector('.wordmark__glyph svg'),
    glyphColour: document.querySelector('.wordmark__glyph') ? getComputedStyle(document.querySelector('.wordmark__glyph')).color : null,
    shellAttr: document.documentElement.dataset.knackShell ?? null,
    knackShell: typeof window.knackShell,
    platform: window.knackShell?.platform ?? null,
    sidePaddingTop: document.querySelector('.side') ? getComputedStyle(document.querySelector('.side')).paddingTop : null,
    width: innerWidth, height: innerHeight,
    narrowLayout: getComputedStyle(document.querySelector('.topbar')).display !== 'none',
    favicon: document.querySelector('link[rel=icon]')?.getAttribute('href')?.slice(0, 40) ?? null,
  })`)) as Record<string, unknown>
  check('the page says Knack: title and wordmark', typeof page.title === 'string' && (page.title as string).includes('Knack') && page.wordmark === 'Knack', page)
  check('the wordmark draws the brand glyph in the text colour', page.glyph === true, { glyph: page.glyph, colour: page.glyphColour })
  check('the preload gives the page the platform and the page marks the inset title bar (macOS)', page.knackShell === 'object' && (process.platform !== 'darwin' || page.shellAttr === 'mac-inset'), { platform: page.platform, shellAttr: page.shellAttr })
  check('the favicon is the brand mark as a data URL', typeof page.favicon === 'string' && (page.favicon as string).startsWith('data:image/svg+xml'), page.favicon)
  check('the smallest window still shows the wide layout (no narrow menu-button layout)', page.narrowLayout === false, { width: page.width })
  check('no content security policy violation and no console error while it loaded', consoleErrors.length === 0, consoleErrors.slice(0, 5))

  // ---- 2. the proxy adds the token, and only the proxy: the page never sees it
  const viaPage = (await wc.executeJavaScript(`fetch('/engine/health').then(async (r) => ({ status: r.status, body: await r.json(), hasTokenHeader: r.headers.has('x-understudy-token') }))`)) as { status: number; body: { ok?: boolean }; hasTokenHeader: boolean }
  check('the page reads the engine through /engine, and the token never comes back to it', viaPage.status === 200 && viaPage.body.ok === true && viaPage.hasTokenHeader === false, viaPage)
  const eng = seen.filter((s) => s.name === 'engine' && s.url === '/health').at(-1)
  check('the engine received the real token, its own Host, and no Origin on a read', eng?.headers['x-understudy-token'] === TOKEN && eng?.headers.host === `127.0.0.1:${engine.port}` && eng?.headers.origin === undefined, { token: eng?.headers['x-understudy-token'] === TOKEN, host: eng?.headers.host, origin: eng?.headers.origin })
  const write = (await wc.executeJavaScript(`fetch('/agent/agents/spawn', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Understudy-Actor': 'worker', 'x-understudy-token': 'forged' }, body: JSON.stringify({ kind: 'shadow' }) }).then((r) => r.status)`)) as number
  const spawnReq = seen.filter((s) => s.name === 'agent' && s.url === '/agents/spawn').at(-1)
  check('a write reaches the agent with the dashboard Origin, the JSON body, and a forged token replaced by the real one', write === 200 && spawnReq?.headers.origin === `http://127.0.0.1:${config.ports.dashboard}` && spawnReq?.headers['x-understudy-token'] === TOKEN && spawnReq?.body === '{"kind":"shadow"}', { status: write, origin: spawnReq?.headers.origin, tokenOk: spawnReq?.headers['x-understudy-token'] === TOKEN })
  const outside = (await wc.executeJavaScript(`fetch('/not-a-prefix/x').then((r) => r.status)`)) as number
  check('nothing but /engine and /agent is forwarded', outside === 200 || outside === 404, outside) // the dashboard's index for a route-like path, never a service

  // ---- 3. pictures of the dashboard, light and dark, at the window's own size
  for (const theme of ['light', 'dark'] as const) {
    nativeTheme.themeSource = theme
    await sleep(500)
    fs.writeFileSync(path.join(out, `dashboard-${theme}.png`), (await wc.capturePage()).toPNG())
  }
  nativeTheme.themeSource = 'system'

  // ---- 4. the starting page and the error page (pictures), then back to the dashboard
  shell.mainWindow.loadStarting()
  await waitFor(() => (wc.getURL() === STARTING_URL && !wc.isLoading() ? true : null), 8000)
  shell.mainWindow.pushUiState({ kind: 'starting', text: 'Starting Knack…', notice: 'Running with example data' })
  await sleep(400)
  const startText = (await wc.executeJavaScript(`document.getElementById('text').textContent + '|' + document.getElementById('notice').textContent + '|' + document.getElementById('retry').hidden`)) as string
  check('the starting page says Starting Knack… and the one calm notice, with no button', startText === 'Starting Knack…|Running with example data|true', startText)
  fs.writeFileSync(path.join(out, 'starting-light.png'), (await wc.capturePage()).toPNG())
  nativeTheme.themeSource = 'dark'
  await sleep(400)
  fs.writeFileSync(path.join(out, 'starting-dark.png'), (await wc.capturePage()).toPNG())
  nativeTheme.themeSource = 'system'
  shell.mainWindow.pushUiState({ kind: 'error', message: 'The engine did not start.', hint: 'See data/logs/knack-engine.log.' })
  await sleep(400)
  const errText = (await wc.executeJavaScript(`document.getElementById('text').textContent + '|' + document.getElementById('hint').textContent + '|' + document.getElementById('retry').hidden`)) as string
  check('the error page says one plain sentence, a hint and one Try again button', errText === 'The engine did not start.|See data/logs/knack-engine.log.|false', errText)
  fs.writeFileSync(path.join(out, 'error-light.png'), (await wc.capturePage()).toPNG())

  // ---- 5. the pill
  const killListeners = new Set<() => void>()
  let killed = false
  shell.attach({
    kill: { trigger: async () => { calls.killTriggered += 1; killed = true; killListeners.forEach((l) => l()) }, isKilled: () => killed, subscribe: (cb) => (killListeners.add(cb), () => killListeners.delete(cb)) },
    probe: async () => ({ suppressed, presenting: false }),
    pendingQueue: async () => pending,
  })
  const feed = async (sup: string, runs: { run_id: string; state: string }[], reachable = true): Promise<void> => {
    supervisor = sup
    shell.feedAgentSample({ health: reachable ? { supervisor: { state: sup } } : null, runs })
    await sleep(250)
  }
  const info = () => shell.info()
  const shoot = async (name: string): Promise<void> => {
    // the pill's own page, light and dark
    const pw = BrowserWindow.getAllWindows().find((b) => b.getTitle().endsWith('status'))
    if (!pw) return
    for (const theme of ['light', 'dark'] as const) {
      nativeTheme.themeSource = theme
      await sleep(250)
      fs.writeFileSync(path.join(out, `pill-${name}-${theme}.png`), (await pw.webContents.capturePage()).toPNG())
    }
    nativeTheme.themeSource = 'system'
  }
  await sleep(500)
  check('the pill is not on screen while idle', info().pill.kind === 'idle' && info().pill.visible === false, info().pill)

  await feed('running', [{ run_id: 'r_1', state: 'running' }])
  check('a run starting shows the pill as working, bottom-right, 280 by 44', info().pill.kind === 'working' && info().pill.visible && info().pill.bounds?.width === 280 && info().pill.bounds?.height === 44, info().pill)
  await shoot('working')
  check('the pill passes clicks through until the pointer is over the Stop button or the label', info().pill.clickThrough === true)
  const pillWc = BrowserWindow.getAllWindows().find((b) => b.getTitle().endsWith('status'))!.webContents
  await pillWc.executeJavaScript(`window.knackPill.setInteractive(true)`)
  await sleep(150)
  check('pointer over a clickable part: the pill takes the click', info().pill.clickThrough === false)
  await pillWc.executeJavaScript(`window.knackPill.setInteractive(false)`)
  await sleep(150)
  check('pointer away: clicks pass through again', info().pill.clickThrough === true)
  await pillWc.executeJavaScript(`window.knackPill.action({ type: 'stop' })`)
  await sleep(300)
  check('the Stop button reaches the kill switch, and the pill then says Stopped', calls.killTriggered === 1 && info().pill.kind === 'killed', { calls, kind: info().pill.kind })
  await shoot('killed')

  killed = false
  await feed('idle', [])
  await feed('running', [{ run_id: 'r_2', state: 'running' }])
  suppressed = 'secure_input'
  await sleep(1700) // the pill re-reads the desk while it shows
  check('a password field with focus hides the pill', info().pill.visible === false, info().pill)
  suppressed = null
  await sleep(1700)
  check('and it comes back when the field loses focus', info().pill.visible === true, info().pill)

  pending = 4
  await feed('running', [{ run_id: 'r_2', state: 'running' }])
  check('an approval raised mid-run asks for the worker', info().pill.kind === 'needs-you', info().pill)
  await shoot('needs-you')
  check('needs-you restores the window (quietly, and never shown in this hidden run)', actions.some((a) => a.action === 'restore'), actions)
  pending = 3
  await feed('running', [{ run_id: 'r_2', state: 'running' }])
  await feed('idle', [{ run_id: 'r_2', state: 'done' }])
  check('a run that ends with nothing new to approve says All done', info().pill.kind === 'done', info().pill)
  await shoot('done')
  check('and does not restore the window', actions.filter((a) => a.action === 'restore').length === 1, actions)

  await feed('running', [{ run_id: 'r_3', state: 'running' }])
  await feed('failed', [{ run_id: 'r_3', state: 'failed' }])
  check('a failed run shows the error state', info().pill.kind === 'error', info().pill)
  await shoot('error')
  await pillWc.executeJavaScript(`window.knackPill.action({ type: 'open' })`)
  await sleep(300)
  check('pressing the label opens Knack and clears the error', actions.at(-1)?.event === 'pill-click' && info().pill.kind === 'idle', { last: actions.at(-1), kind: info().pill.kind })

  // ---- 6. the settings that matter to the shell
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
