// Electron half of `npm run preflight`: permissions, a real screen grab, and global-shortcut registration, all from the
// same Electron binary and the same parent process (the "responsible app" macOS grants permissions to) that the demo uses.
// Prints exactly one line, `PREFLIGHT_PROBE {json}`, then exits. No window is created.
const { app, desktopCapturer, globalShortcut, systemPreferences } = require('electron')
const fs = require('node:fs')
const path = require('node:path')

app.dock?.hide()

const result = { electron: process.versions.electron, platform: process.platform, bundleId: process.env.__CFBundleIdentifier ?? null, termProgram: process.env.TERM_PROGRAM ?? null }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function accelerators(name) {
  const src = fs.readFileSync(path.join(__dirname, '..', 'src', 'main', 'hotkey.ts'), 'utf8')
  const m = src.match(new RegExp(`${name}_ACCELERATORS = \\[([^\\]]*)\\]`))
  return m ? [...m[1].matchAll(/'([^']+)'/g)].map((x) => x[1]) : []
}

function imageStats(img) {
  const { width, height } = img.getSize()
  const buf = img.toBitmap()
  const stride = Math.max(1, Math.floor(buf.length / 4 / 4000)) * 4
  let n = 0
  let sum = 0
  let sumSq = 0
  for (let i = 0; i + 2 < buf.length; i += stride) {
    const lum = 0.114 * buf[i] + 0.587 * buf[i + 1] + 0.299 * buf[i + 2]
    sum += lum
    sumSq += lum * lum
    n++
  }
  const mean = sum / Math.max(n, 1)
  return { width, height, meanLuma: Math.round(mean), stdLuma: Math.round(Math.sqrt(Math.max(sumSq / Math.max(n, 1) - mean * mean, 0)) * 10) / 10 }
}

async function grabScreen() {
  const attempts = []
  for (let attempt = 1; attempt <= 3; attempt++) {
    const t0 = Date.now()
    try {
      const sources = await Promise.race([
        desktopCapturer.getSources({ types: ['screen'], thumbnailSize: { width: 640, height: 360 } }),
        sleep(4000).then(() => {
          throw new Error('getSources timed out after 4 s')
        }),
      ])
      const source = sources[0]
      if (!source || source.thumbnail.isEmpty()) {
        attempts.push({ attempt, ms: Date.now() - t0, error: 'no screen source returned' })
      } else {
        attempts.push({ attempt, ms: Date.now() - t0, ...imageStats(source.thumbnail), sources: sources.length })
        break
      }
    } catch (err) {
      attempts.push({ attempt, ms: Date.now() - t0, error: err instanceof Error ? err.message : String(err) })
    }
    await sleep(300)
  }
  return attempts
}

function probeHotkeys() {
  const out = { start: [], stop: [], failed: [] }
  for (const [kind, list] of [
    ['start', accelerators('START')],
    ['stop', accelerators('STOP')],
  ]) {
    for (const acc of list) {
      let ok = false
      try {
        ok = globalShortcut.register(acc, () => undefined) && globalShortcut.isRegistered(acc)
      } catch {
        ok = false
      }
      ;(ok ? out[kind] : out.failed).push(acc)
    }
  }
  globalShortcut.unregisterAll()
  return out
}

const watchdog = setTimeout(() => {
  console.log('PREFLIGHT_PROBE ' + JSON.stringify({ ...result, error: 'probe timed out after 25 s' }))
  app.exit(0)
}, 25000)

app.whenReady().then(async () => {
  try {
    if (process.platform === 'darwin') {
      result.screenStatus = systemPreferences.getMediaAccessStatus('screen')
      result.micStatus = systemPreferences.getMediaAccessStatus('microphone')
      result.accessibilityTrusted = systemPreferences.isTrustedAccessibilityClient(false)
    }
    result.grab = await grabScreen()
    result.hotkeys = probeHotkeys()
  } catch (err) {
    result.error = err instanceof Error ? err.message : String(err)
  }
  clearTimeout(watchdog)
  console.log('PREFLIGHT_PROBE ' + JSON.stringify(result))
  app.exit(0)
})
