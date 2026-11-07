// Scores results/stage_<preset>.jsonl: hit-rate by kind, IoU, negatives, latency, escalation share.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const dir = path.join(here, 'results');
const pct = (a, p) => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.min(s.length - 1, Math.floor(p * s.length))] : NaN; };
const inside = (p, b) => p.x >= b.xmin && p.x <= b.xmax && p.y >= b.ymin && p.y <= b.ymax;
function iou(a, b) {
  const ix = Math.max(0, Math.min(a.xmax, b.xmax) - Math.max(a.xmin, b.xmin)), iy = Math.max(0, Math.min(a.ymax, b.ymax) - Math.max(a.ymin, b.ymin));
  const inter = ix * iy, u = (a.xmax - a.xmin) * (a.ymax - a.ymin) + (b.xmax - b.xmin) * (b.ymax - b.ymin) - inter;
  return u > 0 ? inter / u : 0;
}
const f = (v, d = 0) => (Number.isFinite(v) ? v.toFixed(d) : '-');
const detail = process.argv.includes('--misses');
for (const preset of ['fast', 'accurate']) {
  const file = path.join(dir, `stage_${preset}.jsonl`);
  if (!fs.existsSync(file)) continue;
  const rows = fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).map(JSON.parse);
  console.log(`\n=== preset ${preset} (n=${rows.length}) ===`);
  console.log('group'.padEnd(10), 'n'.padStart(3), 'hit%'.padStart(6), 'IoU'.padStart(5), 'p50ms'.padStart(6), 'p95ms'.padStart(6), '>6s'.padStart(4), 'flash%'.padStart(7));
  const groups = { ui: rows.filter((r) => r.kind === 'ui'), phrase: rows.filter((r) => r.kind === 'phrase'), '1440': rows.filter((r) => r.w === 1440 && !r.negative), '1920': rows.filter((r) => r.w === 1920 && !r.negative), 'ALL pos': rows.filter((r) => !r.negative) };
  for (const [name, g] of Object.entries(groups)) {
    if (!g.length) continue;
    let hit = 0; const ious = [];
    for (const r of g) {
      const ok = r.found && r.point && inside(r.point, r.gt);
      if (ok) hit++;
      if (r.found && r.box) ious.push(iou(r.box, r.gt));
      if (detail && !ok) console.log('   MISS', r.shotId, '|', r.desc, '| found', r.found, JSON.stringify(r.point), 'GT', JSON.stringify({ x: [r.gt.xmin | 0, r.gt.xmax | 0], y: [r.gt.ymin | 0, r.gt.ymax | 0] }), '|', r.model, r.reason ?? '');
    }
    const lat = g.map((r) => r.latencyMs);
    const flash = g.filter((r) => /3\.8-flash/.test(r.model)).length;
    console.log(name.padEnd(10), String(g.length).padStart(3), f(hit / g.length * 100).padStart(6), f(ious.reduce((a, b) => a + b, 0) / (ious.length || 1), 2).padStart(5), String(pct(lat, 0.5)).padStart(6), String(pct(lat, 0.95)).padStart(6), String(lat.filter((l) => l > 6000).length).padStart(4), f(flash / g.length * 100).padStart(7));
  }
  const neg = rows.filter((r) => r.negative);
  const bad = neg.filter((r) => r.found);
  console.log(`negatives: ${neg.length - bad.length}/${neg.length} correctly not found`, bad.map((r) => `${r.shotId}:${r.desc}`).join('; '));
  const unlabeled = rows.filter((r) => r.found && !r.label).length;
  console.log(`found without label: ${unlabeled}`);
}
