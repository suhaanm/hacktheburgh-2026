// Real-screen accuracy harness: does point_at land on the right thing? Run with `npm run e2e -- --accuracy --mode real --visible`.
// The demo-stage is shown fullscreen on the primary display (src/main/dev), REAL capture grabs it, the Grounder boxes the target,
// and we compare the box the overlay was asked to draw with the stage's own ground-truth rect. Results -> docs/QA_ACCURACY.md.
// Mock mode runs the same plumbing but the numbers are meaningless (canned boxes) and are labelled so.
import fs from 'node:fs'
import path from 'node:path'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import type { NormBox } from './helpers'
import { MODE, REPO, VISIBLE, centre, clearOverlayLog, decodePng, dev, enclosedHole, fetchLog, insideBox, iou, overlayLog, percentile, resetApp, sleep, tool } from './helpers'

interface FlowStep {
  index: number
  id: string
  targetId: string
  targetDescription: string
  instruction: string
}
interface Flow {
  skillId: string
  goal: string
  steps: FlowStep[]
}
interface CatalogEntry {
  id: string
  kind: string
  label: string
  desc: string | null
  visible: boolean
  box: NormBox | null
}

interface Row {
  group: string
  targetId: string
  description: string
  found: boolean
  pred?: NormBox
  gt?: NormBox
  iou?: number
  centreHit?: boolean
  centreDistNorm?: number
  confidence?: number
  ms: number
  note?: string
}

const rows: Row[] = []
const absentRows: Row[] = []
const renderRows: { targetId: string; predPx: string; ringPx: string; enclosed: boolean; holeIou: number; centreOffsetPx: number; gtCentreInside: boolean }[] = []
let apiCallsBefore = 0
let viewportInfo = ''
let capturePath = ''

// Ground truth in DISPLAY-normalised coordinates (the stage window sits on the work area, not the whole display).
async function stageRects(): Promise<Record<string, NormBox>> {
  const r = (await dev<{ rects: Record<string, NormBox>; sizeMatches: boolean }>('/dev/stage/screen-rects')).body
  expect(r.sizeMatches, 'page viewport equals the window content size').toBe(true)
  return r.rects
}

async function measure(group: string, targetId: string, description: string): Promise<Row> {
  const gt = (await stageRects())[targetId]
  await clearOverlayLog()
  const { result, ms } = await tool<{ found: boolean; confidence: number; note?: string }>('point_at', { target: description })
  const ring = (await overlayLog()).filter((o) => o.op === 'show').flatMap((o) => o.annotations ?? []).filter((a) => a.kind === 'ring' && a.box).pop()
  const pred = ring?.box
  const row: Row = { group, targetId, description, found: Boolean(result.found), confidence: result.confidence, ms, note: result.error ?? result.note, gt }
  if (pred && gt) {
    row.pred = pred
    row.iou = iou(pred, gt)
    row.centreHit = insideBox(centre(pred), gt)
    const a = centre(pred)
    const b = centre(gt)
    row.centreDistNorm = Math.hypot(a.x - b.x, a.y - b.y)
  }
  return row
}

const fmt = (n: number | undefined, d = 2) => (n === undefined || Number.isNaN(n) ? '-' : n.toFixed(d))
const boxStr = (b?: NormBox) => (b ? `${Math.round(b.xmin)},${Math.round(b.ymin)},${Math.round(b.xmax)},${Math.round(b.ymax)}` : '-')

const QUICK = process.env.ACC_QUICK === '1' // flows only, 2 absent targets, 3 render checks: ~20 API calls

describe('point_at accuracy on the real screen', () => {
  beforeAll(async () => {
    await resetApp()
    const opened = await dev<{ viewport: { w: number; h: number }; display: { w: number; h: number; scale: number } }>('/dev/stage/open', {})
    expect(opened.status, 'stage window opens').toBe(200)
    const c = (opened.body as unknown as { content: { x: number; y: number; width: number; height: number } }).content
    viewportInfo = `stage window ${c.width}x${c.height} css px at (${c.x},${c.y}) (work area) on a ${opened.body.display.w}x${opened.body.display.h} display (scale ${opened.body.display.scale})`
    expect(opened.body.viewport.w, 'page viewport equals the window content width').toBe(c.width)
    const svc = (await dev<{ screenPermission: string; captureMode: string; usingStageCapture: boolean }>('/dev/services')).body
    capturePath = svc.usingStageCapture ? `stage-window capturePage (Screen Recording status: ${svc.screenPermission})` : `REAL desktopCapturer of the primary display (Screen Recording status: ${svc.screenPermission})`
    await dev('/dev/dock', { visible: false })
    apiCallsBefore = (await fetchLog()).length
  })

  afterAll(async () => {
    await dev('/dev/dock', { visible: true })
    await dev('/dev/stage/close', {})
    writeReport((await fetchLog()).length - apiCallsBefore)
  })

  it('the stage is visible to the real capture (screenshot is not blank and matches the display aspect)', async () => {
    const res = await fetch(`${process.env.E2E_DEBUG_URL}/shot?purpose=ground`)
    expect(res.status).toBe(200)
    const buf = Buffer.from(await res.arrayBuffer())
    const file = path.join(REPO, 'docs', 'qa-accuracy-shot.jpg')
    fs.writeFileSync(file, buf)
    expect(buf.length, 'a real screenshot has detail (a blank/black capture is tiny: screen-recording permission?)').toBeGreaterThan(40_000)
  })

  it('flow targets: every step target of every flow is found and boxed on the right element', async (ctx) => {
    const flows = (await dev<Record<string, Flow>>('/dev/stage/flows')).body
    if (!flows) return ctx.skip('stage exposes no STAGE_FLOWS')
    for (const [flowId, flow] of Object.entries(flows)) {
      for (const step of flow.steps) {
        await dev('/dev/stage/call', { fn: 'setStep', args: [flowId, step.index - 1] })
        await sleep(350)
        rows.push(await measure(flowId, step.targetId, step.targetDescription))
      }
    }
    expect(rows.length).toBeGreaterThanOrEqual(12)
  }, 600_000)

  it.skipIf(QUICK)('catalog targets: buttons/links/toggles/sliders on assorted screens, described by the stage descriptions', async () => {
    const fixtures = ['desktop', 'video/contacts', 'video/precall', 'video/call-screen', 'messages/scam', 'settings/display', 'settings/general']
    const seen = new Set(rows.map((r) => r.targetId))
    let added = 0
    for (const route of fixtures) {
      await dev('/dev/stage/call', { fn: 'go', args: [route] })
      await sleep(350)
      const catalog = (await dev<CatalogEntry[]>('/dev/stage/catalog')).body
      const labelCount = new Map<string, number>()
      for (const c of catalog.filter((e) => e.visible)) labelCount.set(c.label, (labelCount.get(c.label) ?? 0) + 1)
      // Label-only descriptions that two on-screen things share ("VideoChat": desktop icon vs task bar) are ambiguous for a human too; skip them.
      const pick = catalog.filter(
        (c) => c.visible && c.box && /button|link|toggle|switch|slider|icon|tab|input|row/i.test(c.kind) && (c.desc || (c.label && labelCount.get(c.label) === 1)) && !seen.has(c.id) && !c.id.endsWith('.thumb'),
      )
      // Spread over the screen: at most 3 per fixture, preferring ones far apart.
      for (const c of pick.slice(0, 3)) {
        seen.add(c.id)
        rows.push(await measure(`catalog:${route}`, c.id, c.desc ?? c.label))
        added++
      }
    }
    expect(added).toBeGreaterThanOrEqual(5)
  }, 600_000)

  it('absent targets: the Grounder says found:false instead of inventing a box', async () => {
    await dev('/dev/stage/call', { fn: 'go', args: ['video/lily'] })
    await sleep(350)
    const absent = [
      'orange button labelled Download report in the top right corner',
      'a Print icon next to the window title',
      'the purple Unicorn menu in the dock',
      'a text box labelled Credit card number',
      'a green Upload photo button at the bottom centre',
    ]
    for (const description of QUICK ? absent.slice(0, 2) : absent) {
      await clearOverlayLog()
      const { result, ms } = await tool<{ found: boolean; confidence: number; note?: string }>('point_at', { target: description })
      const ring = (await overlayLog()).some((o) => o.op === 'show' && (o.annotations ?? []).some((a) => a.kind === 'ring'))
      absentRows.push({ group: 'absent', targetId: '-', description, found: Boolean(result.found) || ring, confidence: result.confidence, ms, note: result.error ?? result.note })
    }
    const falsePositives = absentRows.filter((r) => r.found).length
    expect(falsePositives, `false positives: ${absentRows.filter((r) => r.found).map((r) => r.description).join(' | ')}`).toBeLessThanOrEqual(1)
  }, 300_000)

  it.skipIf(!VISIBLE)('render check: the ring the overlay really paints encloses the true rect (overlay.png pixels)', async () => {
    const flows = (await dev<Record<string, Flow>>('/dev/stage/flows')).body
    const picks: [string, FlowStep][] = []
    for (const [flowId, flow] of Object.entries(flows ?? {})) for (const i of [1, 2]) if (flow.steps[i]) picks.push([flowId, flow.steps[i]])
    for (const [flowId, step] of picks.slice(0, QUICK ? 3 : 6)) {
      await dev('/dev/stage/call', { fn: 'setStep', args: [flowId, step.index - 1] })
      await sleep(350)
      const gt = (await stageRects())[step.targetId]
      await clearOverlayLog()
      const { result } = await tool<{ found: boolean }>('point_at', { target: step.targetDescription })
      const pred = (await overlayLog()).filter((o) => o.op === 'show').flatMap((o) => o.annotations ?? []).filter((a) => a.kind === 'ring' && a.box).pop()?.box
      if (!result.found || !gt || !pred) continue
      await sleep(1800) // let the flight/pulse animations settle
      const res = await fetch(`${process.env.E2E_DEBUG_URL}/overlay.png`)
      expect(res.status).toBe(200)
      const bytes = Buffer.from(await res.arrayBuffer())
      if (renderRows.length < 3) fs.writeFileSync(path.join(REPO, 'docs', `qa-accuracy-overlay-${step.targetId.replace(/[^\w.-]/g, '_')}.png`), bytes)
      const png = decodePng(bytes)
      const px = (b: NormBox) => ({ x: (b.xmin / 1000) * png.width, y: (b.ymin / 1000) * png.height, w: ((b.xmax - b.xmin) / 1000) * png.width, h: ((b.ymax - b.ymin) / 1000) * png.height })
      const predPx = px(pred)
      const gtPx = px(gt)
      const cx = predPx.x + predPx.w / 2
      const cy = predPx.y + predPx.h / 2
      const hole = enclosedHole(png, cx, cy)
      const predStr = `${Math.round(predPx.x)},${Math.round(predPx.y)} ${Math.round(predPx.w)}x${Math.round(predPx.h)}`
      if (!hole) {
        renderRows.push({ targetId: step.targetId, predPx: predStr, ringPx: 'NOT ENCLOSED', enclosed: false, holeIou: 0, centreOffsetPx: NaN, gtCentreInside: false })
        continue
      }
      const ix = Math.max(0, Math.min(hole.x + hole.w, predPx.x + predPx.w) - Math.max(hole.x, predPx.x))
      const iy = Math.max(0, Math.min(hole.y + hole.h, predPx.y + predPx.h) - Math.max(hole.y, predPx.y))
      const inter = ix * iy
      const gx = gtPx.x + gtPx.w / 2
      const gy = gtPx.y + gtPx.h / 2
      renderRows.push({
        targetId: step.targetId,
        predPx: predStr,
        ringPx: `${hole.x},${hole.y} ${hole.w}x${hole.h}`,
        enclosed: true,
        holeIou: inter / (hole.w * hole.h + predPx.w * predPx.h - inter),
        centreOffsetPx: Math.hypot(hole.x + hole.w / 2 - cx, hole.y + hole.h / 2 - cy),
        gtCentreInside: gx >= hole.x && gx <= hole.x + hole.w && gy >= hole.y && gy <= hole.y + hole.h,
      })
    }
    expect(renderRows.length).toBeGreaterThan(0)
    expect(renderRows.filter((r) => r.enclosed).length, 'a ring is painted around the box the overlay was given').toBe(renderRows.length)
    expect(renderRows.filter((r) => r.holeIou >= 0.4).length, 'the painted ring matches the requested box (norm -> px mapping)').toBe(renderRows.length)
  }, 240_000)
})

function writeReport(googleCalls: number): void {
  const found = rows.filter((r) => r.found && r.pred)
  const ious = found.map((r) => r.iou ?? 0)
  const lat = rows.concat(absentRows).map((r) => r.ms)
  const hit = found.filter((r) => r.centreHit).length
  const iou50 = found.filter((r) => (r.iou ?? 0) >= 0.5).length
  const iou30 = found.filter((r) => (r.iou ?? 0) >= 0.3).length
  const calls = rows.length + absentRows.length
  const mockNote = MODE === 'mock' ? '\n> MOCK RUN: the Grounder returns canned boxes, so these numbers say nothing about the product. Re-run with `npm run e2e -- --accuracy --mode real --visible` once real services are wired.\n' : ''
  const lines: string[] = []
  lines.push('# point_at accuracy on the real screen (QA)')
  lines.push('')
  lines.push(`Run: ${new Date().toISOString()} | mode: ${MODE} | ${viewportInfo}`)
  lines.push('')
  lines.push(`Capture path: ${capturePath}`)
  lines.push(mockNote)
  lines.push('Method: the demo-stage is shown in a frameless window on the work area of the primary display (exact content bounds, so ground truth maps to display-normalised coordinates); the capture path named above grabs it; `point_at` is called with the stage\'s own `targetDescription`; the box handed to the overlay is compared with `__stage.rects()[targetId]` (mapped to display-normalised 0-1000 through the window content bounds).')
  lines.push('')
  lines.push('## Summary')
  lines.push('')
  lines.push('| Metric | Value |')
  lines.push('|---|---|')
  lines.push(`| Present targets tried | ${rows.length} |`)
  lines.push(`| Found (a box was drawn) | ${found.length}/${rows.length} |`)
  lines.push(`| Hit-rate: predicted box centre inside the true rect | ${hit}/${rows.length} (${fmt((100 * hit) / Math.max(1, rows.length), 0)}%) |`)
  lines.push(`| IoU >= 0.5 | ${iou50}/${rows.length} (${fmt((100 * iou50) / Math.max(1, rows.length), 0)}%) |`)
  lines.push(`| IoU >= 0.3 | ${iou30}/${rows.length} (${fmt((100 * iou30) / Math.max(1, rows.length), 0)}%) |`)
  lines.push(`| Median IoU (found) | ${fmt(percentile(ious, 50))} |`)
  lines.push(`| Median centre distance to true centre (0-1000 scale; 10 = 1% of the screen) | ${fmt(percentile(found.map((r) => r.centreDistNorm ?? 0), 50), 1)} |`)
  lines.push(`| Absent targets: correctly found:false | ${absentRows.filter((r) => !r.found).length}/${absentRows.length} |`)
  lines.push(`| Latency p50 / p95 (ms, whole point_at incl. capture) | ${fmt(percentile(lat, 50), 0)} / ${fmt(percentile(lat, 95), 0)} |`)
  lines.push(`| point_at calls / Google API requests | ${calls} / ${googleCalls} (budget 150) |`)
  lines.push('')
  lines.push('Note: IoU is conservative here. The true rect is the element\'s whole hit area (desktop icons include their label, window buttons include padding) while the model boxes the visible glyph, so a correct point can score IoU 0.2-0.5. The pointing metric that matters is "centre inside true rect" and the centre distance.')
  lines.push('')
  lines.push('## Per target')
  lines.push('')
  lines.push('| Group | Target id | Found | IoU | Centre hit | Centre dist (0-1000) | Pred box | True box | ms | Description |')
  lines.push('|---|---|---|---|---|---|---|---|---|---|')
  for (const r of rows) {
    lines.push(`| ${r.group} | ${r.targetId} | ${r.found ? 'yes' : 'NO'} | ${fmt(r.iou)} | ${r.centreHit === undefined ? '-' : r.centreHit ? 'yes' : 'NO'} | ${fmt(r.centreDistNorm, 0)} | ${boxStr(r.pred)} | ${boxStr(r.gt)} | ${r.ms} | ${r.description.slice(0, 70).replace(/\|/g, '/')} |`)
  }
  lines.push('')
  lines.push('## Absent targets (must say found:false)')
  lines.push('')
  lines.push('| Found | ms | Note | Description |')
  lines.push('|---|---|---|---|')
  for (const r of absentRows) lines.push(`| ${r.found ? 'YES (bad)' : 'no (good)'} | ${r.ms} | ${(r.note ?? '').slice(0, 60).replace(/\|/g, '/')} | ${r.description.replace(/\|/g, '/')} |`)
  if (renderRows.length) {
    lines.push('')
    lines.push('## Render check (what the overlay window really painted, from overlay.png, device px)')
    lines.push('')
    lines.push('Method: flood-fill from the centre of the box handed to the overlay; the painted ring encloses it and the fill bounds are the ring hole. Compares the hole with the requested box (norm -> overlay window -> display pixels mapping) and reports whether the TRUE target centre is inside the ring.')
    lines.push('')
    lines.push('| Target | Requested box (x,y WxH px) | Painted ring hole | Ring painted | Hole vs requested IoU | Centre offset px | True target centre inside ring |')
    lines.push('|---|---|---|---|---|---|---|')
    for (const r of renderRows) lines.push(`| ${r.targetId} | ${r.predPx} | ${r.ringPx} | ${r.enclosed ? 'yes' : 'NO'} | ${fmt(r.holeIou)} | ${fmt(r.centreOffsetPx, 0)} | ${r.gtCentreInside ? 'yes' : 'NO'} |`)
  }
  lines.push('')
  const history = path.join(REPO, 'docs', 'qa-accuracy-history.md')
  if (fs.existsSync(history)) lines.push(fs.readFileSync(history, 'utf8'))
  fs.writeFileSync(path.join(REPO, 'docs', 'QA_ACCURACY.md'), lines.join('\n'))
  console.log(`[e2e] wrote docs/QA_ACCURACY.md (hit ${hit}/${rows.length}, median IoU ${fmt(percentile(ious, 50))}, p50 ${fmt(percentile(lat, 50), 0)} ms, p95 ${fmt(percentile(lat, 95), 0)} ms; google requests ${googleCalls})`)
}
