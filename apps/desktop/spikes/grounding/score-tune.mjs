import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const rows = fs.readFileSync(path.join(here, 'results/tune.jsonl'), 'utf8').split('\n').filter(Boolean).map(JSON.parse);
const pct = (a, p) => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.min(s.length - 1, Math.floor(p * s.length))] : NaN; };
const by = {};
for (const r of rows) (by[r.cfg] ??= []).push(r);
console.log('config'.padEnd(26), 'n', 'hit', 'negOK', 'p50', 'p95', 'tok(in/out/think)');
for (const [cfg, rs] of Object.entries(by)) {
  let hit = 0, pos = 0, negOk = 0, neg = 0; const lat = []; const tin = [], tout = [], tth = [];
  for (const r of rs) {
    if (r.error) continue;
    lat.push(r.ms); tin.push(r.tokens.in ?? 0); tout.push(r.tokens.out ?? 0); tth.push(r.tokens.think ?? 0);
    if (r.negative) { neg++; if (!r.raw?.found) negOk++; continue; }
    pos++;
    const b = r.raw?.box_2d;
    if (r.raw?.found && Array.isArray(b) && b.length === 4) {
      const cx = (b[1] + b[3]) / 2, cy = (b[0] + b[2]) / 2;
      if (cx >= r.gt.xmin && cx <= r.gt.xmax && cy >= r.gt.ymin && cy <= r.gt.ymax) hit++;
    }
  }
  const avg = (a) => Math.round(a.reduce((x, y) => x + y, 0) / (a.length || 1));
  console.log(cfg.padEnd(26), String(rs.length).padStart(2), `${hit}/${pos}`.padStart(4), `${negOk}/${neg}`.padStart(5), String(pct(lat, 0.5)).padStart(5), String(pct(lat, 0.95)).padStart(5), `${avg(tin)}/${avg(tout)}/${avg(tth)}`, `errors=${rs.filter((r) => r.error).length}`);
}
