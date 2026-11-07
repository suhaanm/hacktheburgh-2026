// A real-Electron check of the Cue panel window, run ONLY through real-check.sh (one Electron at a time, under scripts/electron-lock.sh).
// It starts Cue from the built bundle (out/cue-check) with a fake engine and a fake overlay, lets the real panel window load the real page
// through the real preload, and checks: the view arrives, the window is sized to the page, a click on an option reaches the engine as `answered`
// with its id, the card collapses into the chip, a malformed action from the page is ignored, and stopCue gives everything back.
// The window is NEVER shown (showInactive is switched off here) so nothing flashes over the owner's screen; "shown without taking focus" is
// therefore not proved by this check and stays a manual check at the demo. Nothing captures the screen: only the window's own page is rendered.
const { app, BrowserWindow, globalShortcut } = require('electron')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const repo = path.resolve(__dirname, '../../../..')
const out = path.join(repo, 'out/cue-check')
const shots = path.join(__dirname, 'shots')
app.setPath('userData', fs.mkdtempSync(path.join(os.tmpdir(), 'cue-real-check-')))
app.disableHardwareAcceleration()
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// Never show a window on the owner's screen.
BrowserWindow.prototype.showInactive = function () {}
BrowserWindow.prototype.show = function () {}
BrowserWindow.prototype.moveTop = function () {}

const ASK = {
  kind: 'ask', episode_id: 'ep-real', tier: null, step: null, target: { box_2d: [622, 347, 673, 444], source: 'dom', confidence: 0.93 },
  options: [{ id: 'calc_a', label: 'Run calculator A' }, { id: 'cliff_a', label: 'Check cliff edges (A)' }, { id: 'write_note', label: 'Copy figures to the note' }, { id: 'other', label: 'Something else' }],
  question: { type: 'close_call', text: 'Which of these is next?' }, say: { chip: null, whisper: null }, why: { level: 2, reasons: ['stuck_signal', 'path_close_call'] }, cooldown_s: 90, new: true,
}

// Destroying the only window (stopCue) must not quit this check before it has written its result.
app.on('window-all-closed', () => {})

app.whenReady().then(async () => {
  const results = {}
  const check = (name, ok, detail) => {
    results[name] = detail === undefined ? ok : { ok, detail }
    console.log(`[cue-real-check] ${ok ? 'ok  ' : 'FAIL'} ${name}${detail === undefined ? '' : ' ' + JSON.stringify(detail)}`)
  }
  try {
    const { startCue, stopCue } = require(path.join(out, 'main/cue.js'))
    const listeners = new Map()
    const bus = { on: (e, cb) => { listeners.set(e, cb); return () => listeners.delete(e) }, emit: (e, p) => listeners.get(e)?.(p) }
    const sent = []
    const queue = [ASK]
    const engine = { next: async () => (queue.length ? queue.shift() : null), feedback: async (e) => void sent.push(e) }
    const marks = []
    const ctx = {
      force: true, bus, engine, userDataDir: null, state: {}, sendOverlay: () => {}, sendDock: () => {}, log: (...a) => console.log('[cue-real-check] log', ...a),
      settings: { get: () => ({ cueEnabled: true }), onChange: () => () => {} },
      overlay: { show: (a) => marks.push(['show', a.map((m) => m.kind)]), clear: (ids) => marks.push(['clear', ids]) },
    }
    const handle = startCue(ctx)
    check('startCue returns a handle', Boolean(handle))
    await sleep(2600)
    const win = handle.panel.window()
    check('the panel window exists after the first cue', Boolean(win))
    check('the window is not visible in this check (showInactive is off)', win ? !win.isVisible() : false)
    const rows = await win.webContents.executeJavaScript("document.querySelectorAll('.row').length")
    check('the page shows 3 options and "Something else"', rows === 4, { rows })
    const question = await win.webContents.executeJavaScript("document.querySelector('.question')?.textContent ?? ''")
    check('the question text is the engine template', question === 'Which of these is next?', { question })
    const b = win.getBounds()
    check('the window is sized to the page (about a card plus shadow room)', b.width >= 280 && b.width <= 320 && b.height >= 150 && b.height <= 260, b)
    fs.mkdirSync(shots, { recursive: true })
    fs.writeFileSync(path.join(shots, 'real-window-ask.png'), (await win.webContents.capturePage()).toPNG())
    const registered = ['Alt+1', 'Alt+2', 'Alt+3', 'Alt+0', 'Alt+Escape'].map((a) => globalShortcut.isRegistered(a))
    check('the global answer keys are registered while the card is up (Alt+1..3, Alt+0, Alt+Escape)', registered.every(Boolean), registered)
    check('Alt+4 is not (only three options)', !globalShortcut.isRegistered('Alt+4'))

    // A malformed action from the page is ignored; a real click reaches the engine.
    await win.webContents.executeJavaScript("window.understudyCue.action({ type: 'evil' })")
    await win.webContents.executeJavaScript("window.understudyCue.action({ type: 'answer', id: '<script>' })")
    await sleep(150)
    check('malformed actions from the page are ignored', !sent.some((e) => e.event === 'answered'))
    await win.webContents.executeJavaScript("document.querySelectorAll('.row')[1].click()")
    await sleep(900)
    check('a click on option 2 reaches the engine as answered with its id', sent.some((e) => e.event === 'answered' && e.option_id === 'cliff_a'), sent.map((e) => e.event))
    const chip = await win.webContents.executeJavaScript("document.querySelector('.chip-text')?.textContent ?? ''")
    check('the card collapsed into the chip for the chosen step', chip === 'Check cliff edges (A)', { chip })
    fs.writeFileSync(path.join(shots, 'real-window-collapsed.png'), (await win.webContents.capturePage()).toPNG())
    const stillRegistered = globalShortcut.isRegistered('Alt+1')
    check('the answer keys were given back when the card collapsed', !stillRegistered)

    stopCue()
    await sleep(200)
    check('stopCue releases every key and destroys the window', !globalShortcut.isRegistered('Alt+Escape') && handle.panel.window() === null)
  } catch (err) {
    check('no exception', false, String(err && err.stack ? err.stack : err))
  }
  fs.writeFileSync(path.join(shots, 'real-check.json'), JSON.stringify(results, null, 2))
  const failed = Object.values(results).filter((v) => v === false || (typeof v === 'object' && v.ok === false)).length
  console.log(`[cue-real-check] ${failed === 0 ? 'ALL OK' : failed + ' FAILED'}`)
  app.exit(failed === 0 ? 0 : 1)
})
