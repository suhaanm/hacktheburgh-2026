// Scores results/*.jsonl -> table. usage: node score.mjs [--json]
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const dir = path.join(here, 'results');
const files = fs.readdirSync(dir).filter((f) => f.endsWith('.jsonl'));

const pct = (arr, p) => { if (!arr.length) return NaN; const s = [...arr].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; };
const inside = (pt, b) => pt.x >= b.xmin && pt.x <= b.xmax && pt.y >= b.ymin && pt.y <= b.ymax;
function iou(a, b) {
  const ix = Math.max(0, Math.min(a.xmax, b.xmax) - Math.max(a.xmin, b.xmin));
  const iy = Math.max(0, Math.min(a.ymax, b.ymax) - Math.max(a.ymin, b.ymin));
  const inter = ix * iy;
  const u = (a.xmax - a.xmin) * (a.ymax - a.ymin) + (b.xmax - b.xmin) * (b.ymax - b.ymin) - inter;
  return u > 0 ? inter / u : 0;
}

/** Normalise any method's raw output to { found, point?, box? } */
export function interpret(row) {
  if (row.error) return { found: false, error: true };
  if (row.method === 'cu_flash') {
    const click = (row.calls ?? []).find((c) => ['click', 'double_click', 'right_click', 'move', 'triple_click', 'middle_click'].includes(c.name) && Number.isFinite(c.args?.x) && Number.isFinite(c.args?.y));
    if (!click) return { found: false };
    return { found: true, point: { x: click.args.x, y: click.args.y } };
  }
  const r = row.raw;
  if (!r || !r.found || !Array.isArray(r.box_2d) || r.box_2d.length !== 4) return { found: false, malformed: !r };
  const [ymin, xmin, ymax, xmax] = r.box_2d;
  const box = { xmin, ymin, xmax, ymax };
  if (xmax <= xmin || ymax <= ymin) return { found: false, malformed: true };
  const area = ((xmax - xmin) * (ymax - ymin)) / 1e6;
  if (area > 0.5) return { found: false, oversize: true };
  return { found: true, box, point: { x: (xmin + xmax) / 2, y: (ymin + ymax) / 2 } };
}

const summary = [];
for (const f of files) {
  const rows = fs.readFileSync(path.join(dir, f), 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l));
  const groups = { all: rows, '1440': rows.filter((r) => r.w === 1440), '1920': rows.filter((r) => r.w === 1920), synthetic: rows.filter((r) => r.kind === 'synthetic'), real: rows.filter((r) => r.kind === 'real') };
  for (const [gname, g] of Object.entries(groups)) {
    if (!g.length) continue;
    const pos = g.filter((r) => !r.negative);
    const neg = g.filter((r) => r.negative);
    let hits = 0, errors = 0, falseNeg = 0; const ious = []; const dists = []; const lat = g.filter((r) => !r.error).map((r) => r.ms);
    for (const r of pos) {
      const it = interpret(r);
      if (it.error) { errors++; continue; }
      if (!it.found) { falseNeg++; continue; }
      if (inside(it.point, r.gt)) hits++;
      if (it.box) ious.push(iou(it.box, r.gt));
      dists.push(Math.hypot(it.point.x - (r.gt.xmin + r.gt.xmax) / 2, it.point.y - (r.gt.ymin + r.gt.ymax) / 2));
    }
    let negOk = 0, hallucinated = 0, negErr = 0;
    for (const r of neg) { const it = interpret(r); if (it.error) negErr++; else if (!it.found) negOk++; else hallucinated++; }
    const nPos = pos.length - errors;
    summary.push({
      method: r0(f), group: gname, n: g.length, pos: pos.length, hitRate: nPos ? hits / nPos : NaN,
      miss_notFound: falseNeg, meanIoU: ious.length ? ious.reduce((a, b) => a + b, 0) / ious.length : NaN,
      medDist: pct(dists, 0.5), neg: neg.length, negCorrect: neg.length - negErr ? negOk / (neg.length - negErr) : NaN, hallucinated,
      p50: pct(lat, 0.5), p95: pct(lat, 0.95), errors: errors + negErr,
    });
  }
}
function r0(f) { return f.replace('.jsonl', ''); }

if (process.argv.includes('--json')) console.log(JSON.stringify(summary, null, 1));
else {
  const f = (v, d = 2) => (Number.isFinite(v) ? v.toFixed(d) : '-');
  console.log('method'.padEnd(14), 'group'.padEnd(10), 'n'.padStart(3), 'hit%'.padStart(6), 'FN'.padStart(3), 'IoU'.padStart(5), 'dist'.padStart(6), 'neg'.padStart(4), 'negOK%'.padStart(7), 'halluc'.padStart(6), 'p50ms'.padStart(6), 'p95ms'.padStart(6), 'err'.padStart(3));
  for (const s of summary) console.log(s.method.padEnd(14), s.group.padEnd(10), String(s.n).padStart(3), f(s.hitRate * 100, 0).padStart(6), String(s.miss_notFound).padStart(3), f(s.meanIoU).padStart(5), f(s.medDist, 0).padStart(6), String(s.neg).padStart(4), f(s.negCorrect * 100, 0).padStart(7), String(s.hallucinated).padStart(6), String(s.p50).padStart(6), String(s.p95).padStart(6), String(s.errors).padStart(3));
}
