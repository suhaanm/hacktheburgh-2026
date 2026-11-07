// Runs the REAL renderer path (getUserMedia -> AudioContext 16 kHz -> worklet -> spotter -> transcribe-live) in a hidden
// Electron window with a fake microphone. Token is minted here the way src/main/live-auth.ts does. No UI is shown.
const { app, BrowserWindow, session, ipcMain } = require('electron')
const path = require('node:path')
const os = require('node:os')
const fs = require('node:fs')
const dotenv = require('dotenv')
dotenv.config({ path: path.join(__dirname, '..', '..', '..', '.env'), quiet: true })

const wav = process.env.WAKE_FAKE_WAV
app.setPath('userData', fs.mkdtempSync(path.join(os.tmpdir(), 'wake-harness-')))
app.commandLine.appendSwitch('use-fake-device-for-media-stream')
app.commandLine.appendSwitch('use-fake-ui-for-media-stream')
app.dock?.hide()

// Chromium's file-backed fake mic returned pure silence on this macOS (any WAV format); the page instead synthesises a MediaStream from the WAV.
ipcMain.handle('wake:wav', () => fs.readFileSync(wav))
ipcMain.handle('wake:token', async () => {
  const { GoogleGenAI, Modality } = await import('@google/genai')
  const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY, httpOptions: { apiVersion: 'v1beta' } })
  const now = Date.now()
  const t = await ai.authTokens.create({ config: { uses: 1, expireTime: new Date(now + 600000).toISOString(), newSessionExpireTime: new Date(now + 60000).toISOString(), liveConnectConstraints: { model: 'gemini-3.5-transcribe-live', config: { responseModalities: [Modality.TEXT], inputAudioTranscription: {} } }, httpOptions: { apiVersion: 'v1beta' } } })
  return { token: t.name, model: 'gemini-3.5-transcribe-live', expiresAt: now + 600000 }
})

app.whenReady().then(async () => {
  session.defaultSession.setPermissionRequestHandler((_wc, _p, cb) => cb(true))
  session.defaultSession.setPermissionCheckHandler(() => true)
  const win = new BrowserWindow({ show: false, width: 400, height: 300, webPreferences: { preload: path.join(__dirname, 'preload.cjs'), backgroundThrottling: false } })
  const t0 = Date.now()
  win.webContents.on('console-message', (e) => {
    const msg = e.message ?? ''
    if (/^(WAKE|STATUS|DEBUG|ERROR)/.test(msg)) console.log(`[+${Date.now() - t0}ms]`, msg)
  })
  await win.loadFile(path.join(__dirname, 'page.html'), process.env.WAKE_PROBE ? { search: process.env.WAKE_PROBE === 'raw' ? 'probe&raw' : 'probe' } : undefined)
  setTimeout(() => app.quit(), Number(process.env.WAKE_HARNESS_MS ?? 25000))
})
