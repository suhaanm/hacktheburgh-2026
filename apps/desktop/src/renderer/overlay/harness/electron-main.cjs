// Electron main for the render harness. Run ONLY through scripts/electron-lock.sh (see run.sh).
// Opens a hidden window per fixture, waits for window.__overlayReady, writes capturePage() PNGs.
// Usage: electron electron-main.cjs --out <dir> [--fixtures a,b] [--backdrops light,dark] [--w 1440] [--h 900]
const { app, BrowserWindow } = require('electron')
const fs = require('node:fs')
const path = require('node:path')

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith('--') ? [...acc, [a.slice(2), all[i + 1]]] : acc), []))
const repo = path.resolve(__dirname, '../../../..')
const out = path.resolve(args.out ?? path.join(repo, 'docs/overlay-shots'))
const W = Number(args.w ?? 1440)
const H = Number(args.h ?? 900)
const backdrops = (args.backdrops ?? 'light,dark').split(',')
const page = path.join(repo, 'out/overlay-demo/demo.html')

app.setPath('userData', fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'overlay-harness-')))
app.disableHardwareAcceleration()
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function shoot(win, query, file) {
  await win.loadURL(`file://${page}?${query}`)
  for (let i = 0; i < 80; i++) {
    if (await win.webContents.executeJavaScript('window.__overlayReady === true')) break
    await sleep(100)
  }
  const image = await win.webContents.capturePage()
  const { width } = image.getSize()
  const png = (width > W ? image.resize({ width: W }) : image).toPNG()
  fs.writeFileSync(file, png)
  console.log('[overlay-harness] wrote', path.relative(repo, file))
}

app.whenReady().then(async () => {
  fs.mkdirSync(out, { recursive: true })
  const win = new BrowserWindow({ width: W, height: H, show: false, useContentSize: true, webPreferences: { offscreen: false, backgroundThrottling: false, webSecurity: false } })
  win.setContentSize(W, H)
  await win.loadURL(`file://${page}`)
  const all = await win.webContents.executeJavaScript('window.__fixtures')
  const wanted = args.fixtures ? args.fixtures.split(',') : all
  for (const name of wanted) {
    for (const backdrop of backdrops) {
      const extra = args.extra ? `&${args.extra}` : ''
      await shoot(win, `fixture=${name}&backdrop=${encodeURIComponent(backdrop)}${extra}`, path.join(out, `${name}.${path.basename(backdrop).replace(/\.[a-z]+$/, '')}.png`))
    }
  }
  app.quit()
}).catch((e) => {
  console.error('[overlay-harness] failed', e)
  app.exit(1)
})
