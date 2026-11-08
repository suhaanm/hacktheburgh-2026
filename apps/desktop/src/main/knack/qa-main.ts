// The hidden QA picture run of the Knack desktop surfaces (run by scripts/knack-qa.mjs; never part of the app). Like check-main.ts: a separate Electron main with stand-in
// services on private ports and a private data directory, every window created and working but NEVER shown (activation policy "prohibited", no Dock icon, no menu bar),
// nothing read from or sent to the desktop, no real input, no microphone, no screen capture (only each page's own pixels through capturePage). It takes a picture of every
// desktop surface in light and dark (first run, the permission states, the wake cards, the info cards, the corner column, the background pills, the Ask bar) and checks what a
// picture cannot show: overlaps, clipped text, a second display, one Stop, the real-mouse-click rule of the cards, and every user-visible word.
import fs from 'node:fs'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import { app, BrowserWindow, ipcMain, nativeTheme, screen } from 'electron'
import { registerAppScheme } from './app-protocol-electron'
import { createAgentPills } from './agent-pills'
import { createAskBar } from './ask-bar'
import { createKnackShell, type KnackShell } from './knack-shell'
import { createStack } from './stack'
import { realStackDeps } from './stack-real'
import { createHudModel } from '../hud-model'
import { registerHud } from '../hud'
import { SettingsStore } from '../settings'
import { resolveStackConfig } from './stack-config'
import { createCardWindow } from '../wake/card-window'
import { CARDS, EVERYTHING_CARD, INFO_CARDS, taskConsentCard, taskQuestionCard, taskResultCard } from '../wake/texts'
import type { PermState } from '../../shared/permissions'

if (process.platform === 'darwin') {
  app.setActivationPolicy('prohibited')
  app.dock?.hide()
}
registerAppScheme()

const out = process.env.KNACK_QA_OUT ?? fs.mkdtempSync(path.join(os.tmpdir(), 'knack-qa-'))
const distDir = process.env.KNACK_QA_DIST ?? ''
const glyphFile = process.env.KNACK_QA_GLYPH ?? ''
const results: { name: string; ok: boolean; detail?: unknown }[] = []
const check = (name: string, ok: boolean, detail?: unknown): void => {
  results.push({ name, ok: Boolean(ok), detail })
}
const notes: Record<string, unknown> = {}
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
const themes = ['light', 'dark'] as const

function fakeService(health: () => unknown, route?: (req: http.IncomingMessage, res: http.ServerResponse) => boolean): Promise<{ server: http.Server; port: number }> {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      const chunks: Buffer[] = []
      req.on('data', (c: Buffer) => chunks.push(c))
      req.on('end', () => {
        if (route?.(req, res)) return
        const send = (v: unknown): void => {
          res.setHeader('content-type', 'application/json')
          res.end(JSON.stringify(v))
        }
        if (req.url === '/health') return send(health())
        if (req.url?.startsWith('/agents/runs')) return send([])
        if (req.method === 'POST') return send({ ok: true })
        res.statusCode = 404
        send({ error: { code: 'not_found', message: 'stand-in' } })
      })
    })
    server.listen(0, '127.0.0.1', () => resolve({ server, port: (server.address() as { port: number }).port }))
  })
}

const BANNED = /\b(demo|mock|synthetic|made[- ]up|alongside|lorem)\b/i

async function run(): Promise<void> {
  fs.mkdirSync(out, { recursive: true })
  const work = fs.mkdtempSync(path.join(os.tmpdir(), 'knack-qa-data-'))
  const dataDir = path.join(work, 'data')
  fs.mkdirSync(dataDir, { recursive: true })
  fs.writeFileSync(path.join(dataDir, '.token'), 'qa-token-0123456789abcdef')
  const userData = path.join(work, 'userData')
  app.setPath('userData', userData)

  let engineKilled = false
  const engine = await fakeService(() => ({ ok: true, mock: false }), (req, res) => {
    if (req.method !== 'GET' || req.url !== '/kill') return false
    res.setHeader('content-type', 'application/json')
    res.end(JSON.stringify({ data: { killed: engineKilled, at: engineKilled ? new Date().toISOString() : null }, meta: null }))
    return true
  })
  const taskStreams = new Set<http.ServerResponse>()
  const sendTask = (event: string, data: unknown): void => {
    for (const r of taskStreams) r.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
  }
  const agent = await fakeService(() => ({ ok: true, mock: false, supervisor: { state: 'idle', generation: 1 }, data_dir_id: 'qa' }), (req, res) => {
    if (req.url !== '/tasks/events') return false
    res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' })
    res.write(`event: snapshot\ndata: ${JSON.stringify({ tasks: [] })}\n\n`)
    taskStreams.add(res)
    // The real service sends a heartbeat every 10 seconds; the shell drops a stream that is silent for 25.
    const beat = setInterval(() => res.write(`event: heartbeat\ndata: {}\n\n`), 8000)
    res.on('close', () => (clearInterval(beat), taskStreams.delete(res)))
    return true
  })
  const env: Record<string, string | undefined> = { GEMINI_API_KEY: 'present', UNDERSTUDY_DATA_DIR: dataDir, ENGINE_PORT: String(engine.port), AGENT_PORT: String(agent.port), DASHBOARD_PORT: '9' }

  // Hey Knack stand-ins: the listener's status the page reads (mutable), and what the first run called.
  const wakeCalls: string[] = []
  const wakeStatus = { switchOn: true, listening: true, line: 'Listening for Hey Knack. Stays on this Mac, nothing stored.', fix: null as string | null, welcomed: false }
  ipcMain.handle('wake:state', () => ({ ...wakeStatus }))
  ipcMain.handle('wake:set', (_e, a: { listen?: boolean }) => (wakeCalls.push(`set:${a?.listen === true}`), (wakeStatus.switchOn = a?.listen === true), { ...wakeStatus }))
  ipcMain.handle('wake:context', (_e, c: { firstRun?: boolean }) => (wakeCalls.push(`context:${JSON.stringify(c)}`), true))
  ipcMain.handle('wake:arm', () => (wakeCalls.push('arm'), { ...wakeStatus }))

  await app.whenReady()
  const config = { ...resolveStackConfig({ env, appPath: '/nowhere', isPackaged: true, resourcesPath: undefined, exists: (p) => fs.existsSync(p), readFile: (p) => fs.readFileSync(p, 'utf8') }), distDir, devUrl: null, preferDevServer: false }
  const stack = createStack(realStackDeps(config))
  const settings = new SettingsStore(null)
  let killed = false
  type K = { killed: boolean; at: null; source: null; engine: null; agent: null }
  const killListeners = new Set<(s: K) => void>()
  const kstate = (): K => ({ killed, at: null, source: null, engine: null, agent: null })
  const killSwitch = {
    trigger: async () => ((killed = true), killListeners.forEach((l) => l(kstate())), { source: 'hud' as const, at: 1, localMs: 1, engine: true, agent: true }),
    clear: async () => ((killed = false), killListeners.forEach((l) => l(kstate()))),
    state: kstate,
    subscribe: (cb: (s: K) => void) => (killListeners.add(cb), () => killListeners.delete(cb)),
  }
  const asked: string[] = []
  const permFake: { microphone: PermState; screen: PermState; accessibility: boolean; needsRestart: boolean } = { microphone: 'not-determined', screen: 'not-determined', accessibility: false, needsRestart: false }
  const helperFake: { state: string; code: string | null } = { state: 'stopped', code: null }
  const shell: KnackShell = createKnackShell({
    blocker: { start: () => 1, stop: () => undefined, isStarted: () => false } as never,
    reveal: () => undefined,
    settings,
    userDataDir: userData,
    config,
    hidden: true,
    env,
    glyphSvg: glyphFile ? fs.readFileSync(glyphFile, 'utf8') : '',
    bootCheck: async () => true,
    killAccelerator: () => 'CommandOrControl+Alt+Shift+K',
    stopEverything: () => undefined,
    relaunch: () => undefined,
    showSheet: async () => 'keep_working',
    stack,
    log: () => undefined,
  })
  await shell.planned
  await waitFor(() => (stack.state().phase === 'ready' ? true : null), 8000)
  const bw = BrowserWindow.getAllWindows()[0]!
  const wc = bw.webContents
  const consoleErrors: string[] = []
  wc.on('console-message', (...args: unknown[]) => {
    const e = args[0] as { level?: string | number; message?: string }
    const level = typeof e === 'object' && e !== null ? e.level : args[1]
    const message = (typeof e === 'object' && e !== null ? e.message : args[2]) as string
    if (/Content Security Policy|Refused to/i.test(String(message)) || level === 'error' || level === 3) consoleErrors.push(String(message).slice(0, 240))
  })
  const model = createHudModel({ kill: killSwitch, endpoints: { dashboard: `http://127.0.0.1:${config.ports.dashboard}` }, openExternal: () => undefined, onProposalChoice: () => undefined, push: () => hud.push(), corner: true })
  let hud = registerHud({ model, log: () => undefined, corner: true, hidden: true })
  shell.attach({
    kill: { trigger: () => killSwitch.trigger(), clear: () => killSwitch.clear(), isKilled: () => killed, subscribe: (cb) => killSwitch.subscribe(() => cb()) },
    hud: model,
    probe: async () => ({ suppressed: null, presenting: false }),
    pendingQueue: async () => 2,
    permissions: {
      status: async () => ({ microphone: permFake.microphone, screen: permFake.screen, accessibility: permFake.accessibility, probe: 'ok', needsRestart: permFake.needsRestart, hint: '/Applications/Terminal.app secret hint' }),
      requestMicrophone: async () => (asked.push('microphone'), true),
      requestScreen: async () => (asked.push('screen'), { microphone: permFake.microphone, screen: permFake.screen, accessibility: permFake.accessibility, probe: 'ok', needsRestart: permFake.needsRestart, hint: '' }),
      requestAccessibility: () => (asked.push('accessibility'), false),
      openSettings: (pane) => void asked.push(`open:${pane}`),
    },
    speech: { helper: () => helperFake as never, request: () => void asked.push('speech') },
    ring: { show: () => undefined, clear: () => undefined, displayBounds: () => screen.getPrimaryDisplay().bounds },
  } as never)

  const png = async (w: Electron.WebContents, name: string, preCss?: string): Promise<void> => {
    for (const theme of themes) {
      nativeTheme.themeSource = theme
      await sleep(450)
      if (preCss) await w.executeJavaScript(`document.documentElement.style.background = ${JSON.stringify(theme === 'light' ? '#9aa1ab' : '#3a3f47')}`)
      fs.writeFileSync(path.join(out, `${name}-${theme}.png`), (await w.capturePage()).toPNG())
    }
    nativeTheme.themeSource = 'system'
  }
  const js = <T>(w: Electron.WebContents, code: string): Promise<T> => w.executeJavaScript(code, true) as Promise<T>
  const clickText = (w: Electron.WebContents, sel: string, re: string): Promise<boolean> =>
    js<boolean>(w, `(() => { const el = [...document.querySelectorAll(${JSON.stringify(sel)})].find((e) => new RegExp(${JSON.stringify(re)}, 'i').test(e.textContent || '')); if (!el) return false; el.click(); return true })()`)
  const visibleText = (w: Electron.WebContents): Promise<string> => js<string>(w, `document.body.innerText`)
  /** Elements whose own text is wider or taller than their box (a clipped word), and elements that stick out of the window. */
  const clipReport = (w: Electron.WebContents): Promise<{ clipped: string[]; outside: string[] }> =>
    js(w, `(() => {
      const clipped = [], outside = []
      for (const el of document.querySelectorAll('body *')) {
        const cs = getComputedStyle(el)
        if (cs.display === 'none' || cs.visibility === 'hidden') continue
        if ((el.scrollWidth > el.clientWidth + 1 && ['hidden', 'clip', 'auto', 'scroll'].includes(cs.overflowX) && el.clientWidth > 0) || (el.scrollHeight > el.clientHeight + 1 && ['hidden', 'clip'].includes(cs.overflowY) && el.clientHeight > 0)) clipped.push((el.className || el.tagName) + ':' + (el.textContent || '').trim().slice(0, 40))
        const r = el.getBoundingClientRect()
        if (r.width > 0 && r.height > 0 && (r.right > innerWidth + 1 || r.bottom > innerHeight + 1 || r.left < -1 || r.top < -1)) outside.push((el.className || el.tagName) + ':' + (el.textContent || '').trim().slice(0, 40))
      }
      return { clipped: clipped.slice(0, 8), outside: outside.slice(0, 8) }
    })()`)

  // ---------------------------------------------------------------------------------------------------------------- 1. the main window: first launch and first run
  await waitFor(() => (wc.getURL().startsWith('app://knack/') && !wc.getURL().includes('__shell') && !wc.isLoading() ? true : null), 15000)
  await waitFor(() => js<boolean>(wc, `document.querySelector('.firstrun') !== null`).catch(() => false), 15000)
  await sleep(1200)
  const hash0 = await js<string>(wc, 'location.hash')
  check('first launch in the Knack window opens first run on its own (nothing stored yet)', hash0.startsWith('#/first-run'), hash0)
  const roleText = await visibleText(wc)
  check('first run, role step: the question, the role cards, Not sure yet and Skip', /What work do you do\?/.test(roleText) && /benefits processor/i.test(roleText) && /Not sure yet/.test(roleText) && /Skip/.test(roleText), roleText.slice(0, 300))
  await png(wc, 'firstrun-1-role')
  notes.roleClip = await clipReport(wc)

  // choose a role: the connection chips slot opens with a Continue button
  await clickText(wc, '.rolecard__btn', 'benefits')
  await sleep(900)
  const chipsText = await visibleText(wc)
  await png(wc, 'firstrun-1b-role-chips')
  const hasContinue = await clickText(wc, '.rolecard__chips .btn--primary, .rolecard__chips button', '^\\s*Continue\\s*$')
  if (!hasContinue) await clickText(wc, '.rolecard__btn', 'benefits')
  await waitFor(() => js<boolean>(wc, `/What may Knack do/.test(document.body.innerText)`), 6000)
  await sleep(700)
  const mayText = await visibleText(wc)
  check('first run, consent step: three equal cards (times, screen if offered, Hey Knack) and nothing pre-selected', /What may Knack do\?/.test(mayText) && /Listen for Hey Knack/.test(mayText) && (await js<number>(wc, `document.querySelectorAll('.consent [aria-pressed="true"]').length`)) === 0, { chips: chipsText.slice(0, 200), may: mayText.slice(0, 400) })
  await png(wc, 'firstrun-2-may')
  notes.mayClip = await clipReport(wc)

  // answer: Hey Knack Yes (arms the listener), times Not now; the last answer advances
  await clickText(wc, '.consent[data-kind="voice"] button', 'Yes')
  await sleep(300)
  check('Yes on the Hey Knack card switches the listener on and arms it (macOS then asks by itself)', wakeCalls.includes('set:true') && wakeCalls.includes('arm'), wakeCalls)
  await clickText(wc, '.consent[data-kind="capture"] button', 'Not now')
  await waitFor(() => js<boolean>(wc, `/Check that it works/.test(document.body.innerText)`), 8000)
  await sleep(900)
  const checkText = await visibleText(wc)
  check('first run, last step is "Check that it works" with the permissions and a Show me button', /Check that it works/.test(checkText) && /Microphone/.test(checkText) && /Show me/.test(checkText), checkText.slice(0, 500))
  check('while set-up shows, the shell told Hey Knack to wait for arm() (firstRun: true)', wakeCalls.some((c) => c.includes('"firstRun":true')), wakeCalls)
  await js(wc, `window.dispatchEvent(new Event('focus'))`)
  await sleep(500)
  await png(wc, 'firstrun-3-permissions-not-asked')
  notes.permNotAskedText = (await visibleText(wc)).replace(/\n+/g, ' | ')
  // Allow on the microphone row asks through the bridge
  await clickText(wc, '.perm button', 'Allow')
  await sleep(400)
  check('the Allow button on a permission row asks macOS for that kind only', asked.includes('microphone'), asked)

  // each state faked through the bridge's stand-in
  const setPerms = async (mic: PermState, scr: PermState, acc: boolean, needsRestart: boolean, name: string): Promise<void> => {
    permFake.microphone = mic
    permFake.screen = scr
    permFake.accessibility = acc
    permFake.needsRestart = needsRestart
    await js(wc, `window.dispatchEvent(new Event('focus'))`)
    await sleep(700)
    await png(wc, `firstrun-3-permissions-${name}`)
    notes[`perm_${name}`] = (await visibleText(wc)).replace(/\n+/g, ' | ')
  }
  helperFake.state = 'blocked'
  helperFake.code = 'speech_denied'
  wakeStatus.listening = false
  wakeStatus.line = 'Hey Knack needs speech recognition. Turn it on in System Settings.'
  wakeStatus.fix = 'speech'
  await setPerms('granted', 'denied', false, false, 'mic-ok-speech-denied-screen-denied')
  const settingsButtons = await js<number>(wc, `[...document.querySelectorAll('button')].filter((b) => /Open System Settings/.test(b.textContent || '')).length`)
  check('a permission that was refused shows a button that opens the right System Settings pane (never silence)', settingsButtons >= 2, settingsButtons)
  await clickText(wc, '.perm button, .firstrun__hey button', 'Open System Settings')
  await sleep(300)
  check('the Open System Settings button opens a pane through the bridge', asked.some((a) => a.startsWith('open:')), asked)
  helperFake.state = 'blocked'
  helperFake.code = 'mic_denied'
  wakeStatus.fix = 'microphone'
  wakeStatus.line = 'Hey Knack needs the microphone. Turn it on in System Settings.'
  await setPerms('denied', 'restricted', false, false, 'mic-denied-screen-restricted')
  helperFake.state = 'listening'
  helperFake.code = null
  wakeStatus.listening = true
  wakeStatus.fix = null
  wakeStatus.line = 'Listening for Hey Knack. Stays on this Mac, nothing stored.'
  await setPerms('granted', 'granted', true, false, 'all-granted')
  await setPerms('granted', 'granted', true, true, 'needs-restart')
  notes.permClip = await clipReport(wc)
  const tryHidden = await js<{ ok: boolean; reason?: string }>(wc, `window.knackShell.tryRing()`)
  notes.tryRingHidden = tryHidden
  const finishText = await visibleText(wc)
  check('the last step ends with one primary button, Show my week', /Show my week/.test(finishText), finishText.slice(-200))
  await clickText(wc, 'button', 'Show my week')
  await sleep(1500)
  const hash1 = await js<string>(wc, 'location.hash')
  check('Show my week goes to Home and first run does not come back', hash1.startsWith('#/home'), hash1)
  await png(wc, 'home-after-firstrun')
  notes.homeText = (await visibleText(wc)).replace(/\n+/g, ' | ').slice(0, 800)
  check('Home after first run has none of the words the owner banned (BANNED)', !BANNED.test(await visibleText(wc)), (await visibleText(wc)).match(BANNED)?.[0])
  check('no content security policy violation and no console error through first run', consoleErrors.length === 0, consoleErrors.slice(0, 5))
  // the stopped / Resume banner in the window
  engineKilled = true
  await js(wc, `window.dispatchEvent(new Event('understudy:retry'))`)
  await waitFor(() => js<boolean>(wc, `/Everything is stopped/.test(document.body.innerText)`), 8000)
  await sleep(600)
  const stoppedText = await visibleText(wc)
  check('stopped: the window says Everything is stopped in words and offers Resume (no Stop to press)', /Everything is stopped/.test(stoppedText) && /Resume/.test(stoppedText), stoppedText.slice(0, 300))
  const stopDomWin = await js<{ stopFaces: number; labels: string[]; svgInStop: number }>(wc, `({ stopFaces: document.querySelectorAll('.stop-button').length, labels: [...document.querySelectorAll('.stop-button')].map((b) => (b.textContent || '').trim()), svgInStop: document.querySelectorAll('.stop-button svg, .stop-button img').length })`)
  check('the window Stop button has the word only (the one red square is drawn by CSS, no second icon)', stopDomWin.svgInStop === 0, stopDomWin)
  await png(wc, 'window-stopped-banner')
  engineKilled = false
  await js(wc, `window.dispatchEvent(new Event('understudy:retry'))`)
  await sleep(800)

  // ---------------------------------------------------------------------------------------------------------------- 2. the corner cards (the wake consent, info and task cards)
  const cardWin = createCardWindow({ hidden: true, capturable: true })
  let n = 0
  const cardShot = async (name: string, spec: { title: string; body: string; buttons: ReadonlyArray<{ id: string; label: string }> }): Promise<{ w: number; h: number } | null> => {
    n += 1
    const id = `qa-${n}`
    void cardWin.ask({ id, title: spec.title, body: spec.body, buttons: spec.buttons, expireMs: 60_000 })
    const win = await waitFor(() => (cardWin.window() && cardWin.window()!.webContents.isLoading() === false ? cardWin.window() : null), 8000)
    if (!win) return null
    await sleep(900)
    const b = win.getBounds()
    const clip = await clipReport(win.webContents)
    const text = await visibleText(win.webContents)
    if (clip.clipped.length || clip.outside.length) notes[`clip_${name}`] = clip
    if (BANNED.test(`${spec.title} ${spec.body} ${spec.buttons.map((x) => x.label).join(' ')} ${text}`)) check(`card ${name} has no banned word`, false, text)
    // the card must be fully inside its window
    await png(win.webContents, `card-${name}`, 'bg')
    cardWin.close(id)
    await sleep(150)
    return { w: b.width, h: b.height }
  }
  const sizes: Record<string, unknown> = {}
  for (const k of ['voice', 'screen', 'click'] as const) sizes[k] = await cardShot(`wake-${k}`, CARDS[k])
  for (const [key, c] of Object.entries(INFO_CARDS)) sizes[key] = await cardShot(`info-${key}`, c)
  const claudeCard = taskConsentCard({ kind: 'claude_agent', can: ['Read and write files in the chosen folder'], cannot: ['Use the internet or run commands outside it'], folder: 'Reports', buttons: { allow: 'Allow for this task', decline: 'Not now', more: [{ id: 'everything', label: 'Everything' }] } })
  sizes.taskClaude = await cardShot('task-claude-agent', claudeCard)
  sizes.taskBrowser = await cardShot('task-browser', taskConsentCard({ kind: 'browser', can: ['Open pages in the Knack browser and fill in forms'], cannot: ['Buy anything or send anything'], folder: null, buttons: { allow: 'Allow for this task', decline: 'Not now', more: [] } }))
  sizes.taskEverything = await cardShot('task-everything', EVERYTHING_CARD)
  sizes.taskQuestion = await cardShot('task-question', taskQuestionCard({ text: 'Which folder should I look in for the summary?', options: [{ id: 'a', label: 'Documents' }, { id: 'b', label: 'Downloads' }, { id: 'c', label: 'Desktop' }] }))
  sizes.taskResult = await cardShot('task-result', taskResultCard('The summary is saved in your Reports folder. It covers 12 claims and 3 need a second look.'))
  notes.cardSizes = sizes
  check('every card fits inside its window (no clipped text, nothing outside)', !Object.keys(notes).some((k) => k.startsWith('clip_')), Object.fromEntries(Object.entries(notes).filter(([k]) => k.startsWith('clip_'))))
  const tooBig = Object.entries(sizes).filter(([, v]) => v && ((v as { w: number }).w > 420 || (v as { h: number }).h > 300))
  check('no card is wider than 420 or taller than 300 pixels', tooBig.length === 0, tooBig)

  // the real-mouse-click rule: a script's click and a click inside 600 ms answer nothing; a trusted mouse press answers once
  let answered: { buttonId: string; via: string } | null | 'pending' = 'pending'
  void cardWin.ask({ id: 'qa-click', title: CARDS.voice.title, body: CARDS.voice.body, buttons: CARDS.voice.buttons, expireMs: 60_000 }).then((a) => (answered = a))
  await waitFor(() => cardWin.window()?.webContents.isLoading() === false, 5000)
  await sleep(250)
  const cw = cardWin.window()!.webContents
  const rect = async (label: string): Promise<{ x: number; y: number } | null> => js(cw, `(() => { const b = [...document.querySelectorAll('button')].find((e) => e.textContent === ${JSON.stringify(label)}); if (!b) return null; const r = b.getBoundingClientRect(); return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) } })()`)
  const click = async (p: { x: number; y: number }): Promise<void> => {
    cw.sendInputEvent({ type: 'mouseMove', x: p.x, y: p.y })
    cw.sendInputEvent({ type: 'mouseDown', x: p.x, y: p.y, button: 'left', clickCount: 1 })
    cw.sendInputEvent({ type: 'mouseUp', x: p.x, y: p.y, button: 'left', clickCount: 1 })
    await sleep(250)
  }
  const yes = await rect('Yes')
  if (yes) await click(yes) // inside the first 600 ms
  check('a click in the first 600 ms after a card appears answers nothing (mis-click guard)', answered === 'pending', answered)
  await sleep(700)
  await js(cw, `[...document.querySelectorAll('button')].find((e) => e.textContent === 'Yes').click()`)
  await sleep(300)
  check('a script clicking Yes (not a real mouse) answers nothing', answered === 'pending', answered)
  const notNow = await rect('Not now')
  if (notNow) await click(notNow)
  await sleep(300)
  check('a trusted mouse press on Not now answers once, as a mouse click, with that button', typeof answered === 'object' && answered !== null && answered.buttonId === 'not_now' && answered.via === 'mouse', answered)
  answered = 'pending'
  void cardWin.ask({ id: 'qa-esc', title: CARDS.voice.title, body: CARDS.voice.body, buttons: CARDS.voice.buttons, expireMs: 60_000 }).then((a) => (answered = a))
  await sleep(900)
  await js(cw, `window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))`)
  await sleep(300)
  check('Escape closes a card and answers nothing (null, never consent)', answered === null, answered)

  // ---------------------------------------------------------------------------------------------------------------- 3. the corner column with a wake card above it: no overlap
  nativeTheme.themeSource = 'light'
  const stacked = createCardWindow({ hidden: true, capturable: true, above: () => hud.window()?.getBounds() ?? null })
  shell.dispatch({ type: 'run_started', realScreen: false })
  shell.dispatch({ type: 'run_progress', label: 'Filling in calculator B', n: 3, m: 8 })
  await sleep(1000)
  void stacked.ask({ id: 'qa-stack', title: INFO_CARDS.blocked_mic_denied.title, body: INFO_CARDS.blocked_mic_denied.body, buttons: INFO_CARDS.blocked_mic_denied.buttons, expireMs: 60_000 })
  await waitFor(() => stacked.window()?.webContents.isLoading() === false, 5000)
  await sleep(1400)
  const hb = hud.window()?.getBounds()
  const sb = stacked.window()?.getBounds()
  const overlap = hb && sb ? !(sb.x + sb.width <= hb.x || hb.x + hb.width <= sb.x || sb.y + sb.height <= hb.y || hb.y + hb.height <= sb.y) : null
  check('a wake card over the working pill: no overlap, the card stacks above the pill', overlap === false && sb !== undefined && hb !== undefined && sb.y + sb.height <= hb.y + 3, { hb, sb })
  // a permission-style approval card in the column AND a wake card
  shell.dispatch({ type: 'decision_needed', class: 'approval' })
  await sleep(1400)
  const hb2 = hud.window()?.getBounds()
  const sb2 = stacked.window()?.getBounds()
  const overlap2 = hb2 && sb2 ? !(sb2.x + sb2.width <= hb2.x || hb2.x + hb2.width <= sb2.x || sb2.y + sb2.height <= hb2.y || hb2.y + hb2.height <= sb2.y) : null
  check('the approval card in the column and a wake card together: still no overlap (the wake card follows the column up)', overlap2 === false, { hb2, sb2 })
  if (hud.window() && stacked.window()) {
    await png(hud.window()!.webContents, 'corner-stack-column', undefined)
    await png(stacked.window()!.webContents, 'corner-stack-card', 'bg')
  }
  stacked.dispose()
  model.handle({ type: 'review', id: model.state().approval?.id ?? '' } as never)
  shell.dispatch({ type: 'run_done', needsNothing: true })
  await sleep(3500)

  // ---------------------------------------------------------------------------------------------------------------- 4. the background pills: four and "+n", every state
  const pillsAll = createAgentPills({ source: shell.agentRuns, onOpen: () => undefined, onStop: () => undefined, hidden: true, disabled: false, capturable: false })
  const row = (id: string, state: string, over: Record<string, unknown> = {}) => ({ task_id: id, title: 'Fill in the quarterly benefits form', route: 'browser', state, source: 'typed', attended: false, latest: null, steps_done: 0, result: null, reason: null, started: new Date().toISOString(), finished: null, open: null, needs_consent: null, question: null, ...over })
  notes.taskStreamsBefore = taskStreams.size
  await waitFor(() => (taskStreams.size > 0 ? true : null), 8000)
  notes.taskStreamsAfterWait = taskStreams.size
  notes.shellStack = shell.info().stack.phase
  sendTask('task_started', row('tk_qa001', 'running', { latest: 'Opening the leave page for the claim' }))
  sendTask('task_started', row('tk_qa002', 'running', { route: 'claude_agent', title: 'Summarise the reports folder', latest: 'Reading the second report' }))
  sendTask('task_started', row('tk_qa003', 'waiting_consent', { route: 'desktop', title: 'Send the weekly summary' }))
  sendTask('task_started', row('tk_qa004', 'planning', { route: 'answer', title: 'Work out the overlap' }))
  sendTask('task_started', row('tk_qa005', 'running', { title: 'Check the bank holidays', latest: 'Looking at the calendar' }))
  sendTask('task_started', row('tk_qa006', 'running', { title: 'Compare the two forms', latest: 'Matching the fields' }))
  const pw = await waitFor(() => (pillsAll.window()?.webContents.isLoading() === false && pillsAll.view().items.length === 4 ? pillsAll.window() : null), 10000)
  await sleep(900)
  if (pw) {
    const dom = await js<{ count: number; moreText: string | null; texts: string[] }>(pw.webContents, `(() => { const ps = [...document.querySelectorAll('.pill:not(.more)')]; const m = document.querySelector('.pill.more'); return { count: ps.length, moreText: m ? m.textContent : null, texts: ps.map((p) => p.querySelector('.text')?.textContent) } })()`)
    check('six tasks show four pills and a "+2" pill', dom.count === 4 && /\+\s*2/.test(dom.moreText ?? ''), dom)
    notes.pillsMany = dom
    await png(pw.webContents, 'pills-four-plus-n')
    notes.pillsClip = await clipReport(pw.webContents)
    const pb = pw.getBounds()
    const wa0 = screen.getPrimaryDisplay().workArea
    check('the pills are fully inside the work area, top right', pb.x + pb.width <= wa0.x + wa0.width + 3 && pb.y >= wa0.y, { pb, wa0 })
  } else check('six tasks show four pills and a "+2" pill', false, { view: pillsAll.view(), streams: taskStreams.size, runs: shell.info().tracker })
  sendTask('task_finished', row('tk_qa001', 'done', { result: 'Done. 3 forms filled in', finished: new Date().toISOString() }))
  sendTask('task_finished', row('tk_qa002', 'failed', { route: 'claude_agent', reason: 'The agent could not start', finished: new Date().toISOString() }))
  sendTask('task_finished', row('tk_qa005', 'stopped', { finished: new Date().toISOString() }))
  sendTask('task_finished', row('tk_qa006', 'done', { result: 'Both forms match', finished: new Date().toISOString() }))
  await sleep(900)
  if (pw) await png(pw.webContents, 'pills-mixed-states')
  pillsAll.dispose()

  // ---------------------------------------------------------------------------------------------------------------- 5. a second display: where the cards, the Ask bar, the pills and the column go
  const real = screen.getPrimaryDisplay()
  const fake = { id: 4242, bounds: { x: real.bounds.x + real.bounds.width, y: real.bounds.y - 180, width: 1920, height: 1080 }, workArea: { x: real.bounds.x + real.bounds.width, y: real.bounds.y - 155, width: 1920, height: 1055 }, scaleFactor: 1 }
  const origAll = screen.getAllDisplays.bind(screen)
  const origNear = screen.getDisplayNearestPoint.bind(screen)
  const origCursor = screen.getCursorScreenPoint.bind(screen)
  const sc = screen as unknown as Record<string, unknown>
  let patched = true
  try {
    sc.getAllDisplays = () => [...origAll(), fake]
    sc.getDisplayNearestPoint = () => fake
    sc.getCursorScreenPoint = () => ({ x: fake.workArea.x + 200, y: fake.workArea.y + 200 })
  } catch {
    patched = false
  }
  check('the harness can fake a second display (the screen module accepts the stand-ins)', patched && screen.getDisplayNearestPoint({ x: 0, y: 0 }).id === 4242, patched)
  if (patched) {
    const inside = (b: { x: number; y: number; width: number; height: number } | undefined, wa: typeof fake.workArea, tol = 20): boolean => !!b && b.x >= wa.x - tol && b.y >= wa.y - tol && b.x + b.width <= wa.x + wa.width + tol && b.y + b.height <= wa.y + wa.height + tol
    const card2 = createCardWindow({ hidden: true })
    void card2.ask({ id: 'qa-d2', title: CARDS.voice.title, body: CARDS.voice.body, buttons: CARDS.voice.buttons, expireMs: 30_000 })
    await waitFor(() => card2.window()?.webContents.isLoading() === false, 5000)
    await sleep(1000)
    const cb = card2.window()?.getBounds()
    check('on a second display holding the pointer the wake card sits bottom-right of THAT display, 16 px in', !!cb && inside(cb, fake.workArea, 1) && Math.abs(cb.x + cb.width - (fake.workArea.x + fake.workArea.width - 16)) <= 1 && Math.abs(cb.y + cb.height - (fake.workArea.y + fake.workArea.height - 16)) <= 1, { cb, wa: fake.workArea })
    card2.dispose()
    const ask2 = createAskBar({ hidden: true, disabled: false, capturable: false, submit: () => ({ ok: false, line: 'x' }) })
    ask2.open()
    await sleep(900)
    const ab = ask2.window()?.getBounds()
    check('the Ask bar centres on the second display, in its upper third', !!ab && inside(ab, fake.workArea, 1) && Math.abs(ab.x + ab.width / 2 - (fake.workArea.x + fake.workArea.width / 2)) <= 1, { ab, wa: fake.workArea })
    ask2.dispose()
    const pills2 = createAgentPills({ source: shell.agentRuns, onOpen: () => undefined, onStop: () => undefined, hidden: true, disabled: false, capturable: false })
    sendTask('task_started', row('tk_qa009', 'running', { title: 'Second display check', latest: 'Working here' }))
    await waitFor(() => pills2.view().items.length >= 1 && pills2.window()?.webContents.isLoading() === false, 8000)
    await sleep(900)
    const pb2 = pills2.window()?.getBounds()
    check('the background pills sit top right of the second display', !!pb2 && inside(pb2, fake.workArea, 4) && Math.abs(pb2.x + pb2.width - 3 - (fake.workArea.x + fake.workArea.width - 16)) <= 2, { pb2, wa: fake.workArea })
    pills2.dispose()
    sendTask('task_finished', row('tk_qa009', 'stopped', { finished: new Date().toISOString() }))
    // the column: a new one appears on the display that holds the pointer
    hud.dispose()
    hud = registerHud({ model, log: () => undefined, corner: true, hidden: true })
    shell.dispatch({ type: 'run_started', realScreen: false })
    shell.dispatch({ type: 'run_progress', label: 'Second display', n: 1, m: 2 })
    await sleep(1500)
    const hb3 = hud.window()?.getBounds()
    check('the corner pill column appears bottom-right of the display that holds the pointer', !!hb3 && inside(hb3, fake.workArea, 4) && Math.abs(hb3.x + hb3.width - (fake.workArea.x + fake.workArea.width - 16)) <= 2, { hb3, wa: fake.workArea })
    // a wake card while the column is on THIS display, and the pointer then moves to the first display: the card must not float above a column that is somewhere else
    const card3 = createCardWindow({ hidden: true, above: () => hud.window()?.getBounds() ?? null })
    void card3.ask({ id: 'qa-d3', title: CARDS.voice.title, body: CARDS.voice.body, buttons: CARDS.voice.buttons, expireMs: 30_000 })
    await waitFor(() => card3.window()?.webContents.isLoading() === false, 5000)
    await sleep(900)
    sc.getDisplayNearestPoint = () => real
    sc.getCursorScreenPoint = () => ({ x: real.workArea.x + 100, y: real.workArea.y + 100 })
    await sleep(1300) // the card follows the pointer every half second
    const c3 = card3.window()?.getBounds()
    const h3 = hud.window()?.getBounds()
    notes.cardAfterPointerMoved = { card: c3, column: h3, firstWorkArea: real.workArea, secondWorkArea: fake.workArea }
    const sameDisplayAsColumn = !!c3 && !!h3 && inside(c3, fake.workArea, 2) && c3.y + c3.height + 4 <= h3.y
    check('the pointer moves to the first display while the column stays on the second: the wake card stays with the column (above it, on that display), never floating over a corner that is empty', sameDisplayAsColumn, { c3, h3, second: fake.workArea })
    card3.dispose()
    sc.getAllDisplays = origAll
    sc.getDisplayNearestPoint = origNear
    sc.getCursorScreenPoint = origCursor
  }
  shell.dispatch({ type: 'run_done', needsNothing: true })

  // ---------------------------------------------------------------------------------------------------------------- 6. words: the packaged page titles and the starting page
  const titles = BrowserWindow.getAllWindows().map((w) => w.getTitle())
  notes.windowTitles = titles
  check('no window of the app is titled with a banned word', !titles.some((t) => BANNED.test(t)), titles)

  const failed = results.filter((r) => !r.ok)
  fs.writeFileSync(path.join(out, 'knack-qa.json'), JSON.stringify({ results, failed: failed.length, notes, asked, wakeCalls }, null, 2))
  for (const r of results) console.log(`${r.ok ? 'PASS' : 'FAIL'} ${r.name}${r.ok ? '' : ` ${JSON.stringify(r.detail)}`}`)
  console.log(`${results.length - failed.length}/${results.length} passed; pictures in ${out}`)
  engine.server.close()
  agent.server.close()
  await stack.stop()
  app.exit(failed.length === 0 ? 0 : 1)
}

run().catch((err: unknown) => {
  console.log(`QA CRASHED ${err instanceof Error ? err.stack : String(err)}`)
  try {
    fs.writeFileSync(path.join(out, 'knack-qa.json'), JSON.stringify({ results, crashed: String(err), notes }, null, 2))
  } catch {
    /* ignore */
  }
  app.exit(2)
})
