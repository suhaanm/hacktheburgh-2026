#!/usr/bin/env node
// Exports the app icon and the menu-bar icons from the brand SVGs in packages/design/brand/ (no install needed: Playwright's Chromium
// renders the SVGs, macOS iconutil packs the .icns).
//   build/icon.icns, build/icon.png (1024)          from understudy-mark.svg, on the standard 824-in-1024 macOS tile with its margin
//   resources/tray/trayTemplate.png (+@2x)          from understudy-tray-template.svg: pure black on transparent (a macOS template image)
//   resources/tray/trayActingTemplate.png (+@2x)    the same with a 3 px filled dot: an agent is acting
//   resources/tray/trayGlanceTemplate.png (+@2x)    the same with a 3 px ring: a glance is in flight
//   resources/tray/trayPausedTemplate.png (+@2x)    the same with the shadow ring left out and a small bar: paused
// Run: node scripts/make-icons.mjs [--preview <dir>]   (preview writes an enlarged contact sheet of the small sizes, for looking)
import { execFileSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const here = dirname(fileURLToPath(import.meta.url))
const app = resolve(here, '..')
const brand = resolve(app, '../../packages/design/brand')
const previewDir = process.argv.includes('--preview') ? process.argv[process.argv.indexOf('--preview') + 1] : null
mkdirSync(join(app, 'build'), { recursive: true })
mkdirSync(join(app, 'resources/tray'), { recursive: true })

const mark = readFileSync(join(brand, 'understudy-mark.svg'), 'utf8')
const trayInner = (() => {
  const svg = readFileSync(join(brand, 'understudy-tray-template.svg'), 'utf8')
  return svg.slice(svg.indexOf('>') + 1, svg.lastIndexOf('</svg>'))
})()

// Tray variants are the brand glyph plus a small mark in the top-right corner (3 px at 1x), black only: the system tints it.
const tray = {
  idle: trayInner,
  acting: `${trayInner}<circle cx="15.6" cy="2.6" r="1.5" fill="#000"/>`,
  glance: `${trayInner}<circle cx="15.6" cy="2.6" r="1.1" fill="none" stroke="#000" stroke-width="0.9"/>`,
  paused: `<circle cx="7.4" cy="7.6" r="4.4" fill="#000"/><rect x="11.2" y="8.6" width="1.5" height="5.6" rx="0.4" fill="#000"/><rect x="14" y="8.6" width="1.5" height="5.6" rx="0.4" fill="#000"/>`,
}
const traySvg = (inner) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18" width="18" height="18">${inner}</svg>`
// The app icon: the brand tile at 824 of 1024 with the usual transparent margin.
const iconSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024"><g transform="translate(100 100) scale(${824 / 128})">${mark.slice(mark.indexOf('>') + 1, mark.lastIndexOf('</svg>'))}</g></svg>`

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage()
async function render(svg, size) {
  await page.setViewportSize({ width: size, height: size })
  await page.setContent(`<!doctype html><body style="margin:0;background:transparent"><img style="display:block;width:${size}px;height:${size}px" src="data:image/svg+xml;base64,${Buffer.from(svg).toString('base64')}"></body>`)
  await page.waitForFunction(() => document.images[0]?.complete)
  return page.screenshot({ type: 'png', omitBackground: true, clip: { x: 0, y: 0, width: size, height: size } })
}

const work = mkdtempSync(join(tmpdir(), 'understudy-icons-'))
try {
  // ---- app icon
  const iconset = join(work, 'icon.iconset')
  mkdirSync(iconset)
  const sizes = [
    ['icon_16x16.png', 16], ['icon_16x16@2x.png', 32], ['icon_32x32.png', 32], ['icon_32x32@2x.png', 64],
    ['icon_128x128.png', 128], ['icon_128x128@2x.png', 256], ['icon_256x256.png', 256], ['icon_256x256@2x.png', 512],
    ['icon_512x512.png', 512], ['icon_512x512@2x.png', 1024],
  ]
  for (const [name, px] of sizes) writeFileSync(join(iconset, name), await render(iconSvg, px))
  execFileSync('iconutil', ['-c', 'icns', iconset, '-o', join(app, 'build/icon.icns')])
  writeFileSync(join(app, 'build/icon.png'), await render(iconSvg, 1024))

  // ---- menu-bar icons (18 pt, so 18 px and 36 px)
  const files = []
  for (const [kind, inner] of Object.entries(tray)) {
    const base = kind === 'idle' ? 'trayTemplate' : `tray${kind[0].toUpperCase()}${kind.slice(1)}Template`
    writeFileSync(join(app, `resources/tray/${base}.png`), await render(traySvg(inner), 18))
    writeFileSync(join(app, `resources/tray/${base}@2x.png`), await render(traySvg(inner), 36))
    files.push(base)
  }

  // ---- a contact sheet of the small sizes, enlarged, on light and dark bars (only the icons themselves)
  if (previewDir) {
    mkdirSync(previewDir, { recursive: true })
    const cells = []
    for (const base of files) cells.push({ label: base, src: `data:image/png;base64,${readFileSync(join(app, `resources/tray/${base}@2x.png`)).toString('base64')}`, src1: `data:image/png;base64,${readFileSync(join(app, `resources/tray/${base}.png`)).toString('base64')}` })
    const dock = [16, 32, 64, 128].map((px) => ({ px }))
    const icons = []
    for (const d of dock) icons.push({ px: d.px, src: `data:image/png;base64,${(await render(iconSvg, d.px)).toString('base64')}` })
    await page.setViewportSize({ width: 980, height: 560 })
    await page.setContent(`<!doctype html><body style="margin:0;font:12px system-ui;background:#888">
      ${['#f6f6f6', '#2a2a2e'].map((bg, i) => `<div style="background:${bg};padding:14px;display:flex;gap:28px;align-items:flex-end;filter:${i ? 'invert(1)' : 'none'}">${cells.map((c) => `<div style="text-align:center;color:#c0392b"><img src="${c.src}" style="width:144px;height:144px;image-rendering:pixelated;background:${bg}"><br><img src="${c.src1}" style="width:18px;height:18px;margin:6px"><img src="${c.src}" style="width:18px;height:18px;margin:6px"><br>${c.label}</div>`).join('')}</div>`).join('')}
      <div style="background:#e9e9ee;padding:14px;display:flex;gap:20px;align-items:flex-end">${icons.map((i) => `<div style="text-align:center"><img src="${i.src}" style="width:${i.px}px;height:${i.px}px;image-rendering:${i.px < 40 ? 'pixelated' : 'auto'}"><br>${i.px}</div>`).join('')}<div style="text-align:center"><img src="${icons[3].src}" style="width:256px;height:256px"></div></div></body>`)
    await page.screenshot({ path: join(previewDir, 'icons-sheet.png'), fullPage: true })
    console.log(join(previewDir, 'icons-sheet.png'))
  }
  console.log(JSON.stringify({ icns: 'build/icon.icns', png: 'build/icon.png', tray: files.map((f) => `resources/tray/${f}.png (+@2x)`) }, null, 2))
} finally {
  await browser.close()
  rmSync(work, { recursive: true, force: true })
}
