// Electron helper for real-check.mjs (run only inside scripts/electron-lock.sh). Modes:
//   stage <url> <outdir>            frameless window over the primary display showing the stage; writes rects.json
//   click <outdir>                  small frameless window with one big button; prints CLICKED when it receives a click
//   fullscreen                      native full-screen window (a new Space), to test the overlay above full-screen apps
//   analyze <png> <rects> <id> <hex>  ring bbox of colour <hex> in a PNG vs the stage element <id>; prints JSON
//   count <image> <hex>             number of pixels near colour <hex>; prints JSON
//   composite <shot> <overlay> <out>  overlay.png over shot.jpg -> out.png (for eyeballing)
const { app, BrowserWindow, nativeImage, screen } = require('electron')
const fs = require('node:fs')
const path = require('node:path')

const [mode, ...rest] = process.argv.slice(2)
// Own profile dir: two Electron processes sharing a userData dir make the second one exit (Chromium singleton).
app.setPath('userData', fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'overlay-tool-')))
app.disableHardwareAcceleration()
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const say = (obj) => console.log('[window-tool] ' + (typeof obj === 'string' ? obj : JSON.stringify(obj)))

function hexToRgb(hex) {
  const n = parseInt(hex.replace('#', ''), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

// Bounding box (px) of the connected blob of colour `hex` that contains the point (cx, cy) in image px, found on a
// 4 px grid. Used to pick the ring out of arrow/label pixels of the same tone.
function blobAround(image, hex, tol, cx, cy) {
  const { width, height } = image.getSize()
  const bmp = image.toBitmap()
  const [r, g, b] = hexToRgb(hex)
  const C = 4
  const gw = Math.ceil(width / C)
  const gh = Math.ceil(height / C)
  const on = new Uint8Array(gw * gh)
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4
      if (bmp[i + 3] >= 250 && Math.abs(bmp[i + 2] - r) <= tol && Math.abs(bmp[i + 1] - g) <= tol && Math.abs(bmp[i] - b) <= tol) on[Math.floor(y / C) * gw + Math.floor(x / C)] = 1
    }
  }
  const seen = new Uint8Array(gw * gh)
  let best = null
  for (let start = 0; start < on.length; start++) {
    if (!on[start] || seen[start]) continue
    const stack = [start]
    seen[start] = 1
    let x0 = gw, y0 = gh, x1 = -1, y1 = -1, n = 0
    while (stack.length) {
      const c = stack.pop()
      const cx0 = c % gw
      const cy0 = (c - cx0) / gw
      n++
      if (cx0 < x0) x0 = cx0
      if (cx0 > x1) x1 = cx0
      if (cy0 < y0) y0 = cy0
      if (cy0 > y1) y1 = cy0
      for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
        const nx = cx0 + dx, ny = cy0 + dy
        if (nx < 0 || ny < 0 || nx >= gw || ny >= gh) continue
        const ni = ny * gw + nx
        if (on[ni] && !seen[ni]) { seen[ni] = 1; stack.push(ni) }
      }
    }
    const bbox = { x0: x0 * C, y0: y0 * C, x1: (x1 + 1) * C - 1, y1: (y1 + 1) * C - 1 }
    if (cx >= bbox.x0 && cx <= bbox.x1 && cy >= bbox.y0 && cy <= bbox.y1) {
      const area = (bbox.x1 - bbox.x0) * (bbox.y1 - bbox.y0)
      if (!best || area < best.area) best = { bbox, area, cells: n }
    }
  }
  return { width, height, bbox: best ? best.bbox : null, count: best ? best.cells : 0 }
}

function scan(image, hex, tol = 14) {
  const { width, height } = image.getSize()
  const bmp = image.toBitmap() // BGRA
  const [r, g, b] = hexToRgb(hex)
  let count = 0
  let x0 = width, y0 = height, x1 = -1, y1 = -1
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4
      if (bmp[i + 3] < 250) continue
      if (Math.abs(bmp[i + 2] - r) <= tol && Math.abs(bmp[i + 1] - g) <= tol && Math.abs(bmp[i] - b) <= tol) {
        count++
        if (x < x0) x0 = x
        if (y < y0) y0 = y
        if (x > x1) x1 = x
        if (y > y1) y1 = y
      }
    }
  }
  return { width, height, count, bbox: count ? { x0, y0, x1, y1 } : null }
}

app.whenReady().then(async () => {
  const display = screen.getPrimaryDisplay()
  if (mode === 'stage') {
    const [url, outdir] = rest
    // enableLargerThanScreen: otherwise macOS slides the window below the menu bar and crops its bottom.
    const win = new BrowserWindow({ ...display.bounds, frame: false, show: false, alwaysOnTop: true, hasShadow: false, resizable: false, enableLargerThanScreen: true, webPreferences: { backgroundThrottling: false } })
    win.setAlwaysOnTop(true, 'floating')
    await win.loadURL(url)
    win.setBounds(display.bounds)
    win.showInactive()
    await sleep(1800)
    const origin = win.getContentBounds()
    const data = await win.webContents.executeJavaScript(`(() => { const out = {}; document.querySelectorAll('[data-ground-id]').forEach((el) => { const r = el.getBoundingClientRect(); out[el.getAttribute('data-ground-id')] = { x: r.x, y: r.y, w: r.width, h: r.height } }); return { viewport: { w: innerWidth, h: innerHeight }, rects: out } })()`)
    data.origin = { x: origin.x, y: origin.y }
    data.display = { w: display.bounds.width, h: display.bounds.height }
    fs.writeFileSync(path.join(outdir, 'rects.json'), JSON.stringify(data))
    say('READY stage')
    return
  }
  if (mode === 'click') {
    const b = { x: 300, y: 330, width: 500, height: 300 }
    const win = new BrowserWindow({ ...b, frame: false, show: false, alwaysOnTop: true, hasShadow: false, resizable: false, webPreferences: { backgroundThrottling: false } })
    win.setAlwaysOnTop(true, 'floating')
    await win.loadURL('data:text/html,' + encodeURIComponent('<body style="margin:0"><button id=b style="width:100vw;height:100vh;font:32px sans-serif;background:#2d9d5b;color:#fff;border:0" onclick="document.body.style.background=\'#c0392b\';document.getElementById(\'b\').style.background=\'#c0392b\';document.getElementById(\'b\').textContent=\'CLICKED\';console.log(\'CLICK-TARGET-RECEIVED\')">click target</button></body>'))
    win.webContents.on('console-message', (_e, _l, message) => message.includes('CLICK-TARGET-RECEIVED') && say('CLICKED'))
    win.setBounds(b)
    win.showInactive()
    say({ ready: 'click', center: { x: b.x + b.width / 2, y: b.y + b.height / 2 } })
    return
  }
  if (mode === 'fullscreen') {
    const win = new BrowserWindow({ show: false, backgroundColor: '#00bcd4', fullscreenable: true })
    await win.loadURL('data:text/html,' + encodeURIComponent('<body style="margin:0;background:#00bcd4;font:48px sans-serif"><h1>full-screen test app</h1></body>'))
    win.show()
    win.setFullScreen(true)
    await sleep(3000)
    say({ ready: 'fullscreen', isFullScreen: win.isFullScreen() })
    return
  }
  if (mode === 'count') {
    say(scan(nativeImage.createFromPath(rest[0]), rest[1]))
    app.quit()
    return
  }
  if (mode === 'analyze') {
    const [png, rectsFile, id, hex] = rest
    const { viewport, rects, origin, display: disp } = JSON.parse(fs.readFileSync(rectsFile, 'utf8'))
    const el = rects[id]
    const img = nativeImage.createFromPath(png)
    const size = img.getSize()
    // 'blob' mode: the ring is the connected blob of the tone colour that encloses the element's centre.
    const r = rest[4] === 'blob' && el ? blobAround(img, hex, 10, ((origin.x + el.x + el.w / 2) / disp.w) * size.width, ((origin.y + el.y + el.h / 2) / disp.h) * size.height) : scan(img, hex, 10)
    const toNorm = (b, w, h) => ({ xmin: (b.x0 / w) * 1000, ymin: (b.y0 / h) * 1000, xmax: (b.x1 / w) * 1000, ymax: (b.y1 / h) * 1000 })
    const ring = r.bbox ? toNorm(r.bbox, r.width, r.height) : null
    const element = el ? { xmin: ((origin.x + el.x) / disp.w) * 1000, ymin: ((origin.y + el.y) / disp.h) * 1000, xmax: ((origin.x + el.x + el.w) / disp.w) * 1000, ymax: ((origin.y + el.y + el.h) / disp.h) * 1000 } : null
    const centre = (b) => ({ x: (b.xmin + b.xmax) / 2, y: (b.ymin + b.ymax) / 2 })
    const contains = ring && element ? ring.xmin <= element.xmin && ring.ymin <= element.ymin && ring.xmax >= element.xmax && ring.ymax >= element.ymax : false
    const off = ring && element ? { dx: centre(ring).x - centre(element).x, dy: centre(ring).y - centre(element).y } : null
    say({ id, ring, element, ringContainsElement: contains, centreOffsetNorm: off, ringPixels: r.count })
    app.quit()
    return
  }
  if (mode === 'composite') {
    const [shot, overlay, out] = rest
    const win = new BrowserWindow({ width: 1440, height: 931, show: false, useContentSize: true, webPreferences: { webSecurity: false } })
    const url = (p) => 'file://' + p
    await win.loadURL('data:text/html,' + encodeURIComponent(`<body style="margin:0;position:relative"><img src="${url(shot)}" style="position:absolute;left:0;top:0;width:100%"><img src="${url(overlay)}" style="position:absolute;left:0;top:0;width:100%"></body>`))
    await sleep(600)
    const img = await win.webContents.capturePage()
    fs.writeFileSync(out, img.toPNG())
    say('wrote ' + out)
    app.quit()
    return
  }
  say('unknown mode ' + mode)
  app.quit()
}).catch((e) => {
  console.error('[window-tool] failed', e)
  app.exit(1)
})
