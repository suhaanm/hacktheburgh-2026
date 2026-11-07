// Summarises results/harvest.json: name variants heard, per-accent miss rate, latency, negatives.
import { readFileSync } from 'node:fs';
const r = JSON.parse(readFileSync(new URL('./results/harvest.json', import.meta.url)));
const errs = r.filter((x) => x.error);
console.log('clips', r.length, 'errors', errs.length, errs.slice(0, 3).map((e) => e.error));
const heard = {};
const lat = [];
for (const c of r.filter((x) => x.kind === 'pos' && !x.error)) {
  const m = c.finalText.toLowerCase().replace(/[.,!?]/g, ' ').split(/\s+/).filter(Boolean);
  const i = m.findIndex((w) => ['hey', 'hay', 'hi', 'ok', 'okay', 'a', 'hello'].includes(w));
  const name = i >= 0 ? m.slice(i + 1, i + 3).join(' ') : `(no prefix) ${m.slice(0, 3).join(' ')}`;
  (heard[c.expect] ??= {})[name] = ((heard[c.expect] ??= {})[name] ?? 0) + 1;
  // latency: first interim containing the expected name, relative to end of speech
  const hit = c.events.find((e) => e.kind !== 'final' && e.text.toLowerCase().includes(c.expect));
  const hitAny = c.events.find((e) => e.text.toLowerCase().includes(c.expect));
  if (hit && c.id.indexOf('-q') < 0) lat.push({ id: c.id, speechMs: c.speechMs, hitMs: hit.t, afterEnd: hit.t - c.speechMs, finalAt: c.events.find((e) => e.kind === 'final')?.t ?? null });
}
console.log('name variants heard:', JSON.stringify(heard, null, 1));
const ae = lat.map((l) => l.afterEnd).sort((a, b) => a - b);
const q = (p) => ae[Math.min(ae.length - 1, Math.floor(p * ae.length))];
console.log('bare "Hey <name>" clips with interim hit:', lat.length, 'of', r.filter((x) => x.kind === 'pos' && !x.id.includes('-q')).length);
console.log('first-interim-name latency vs END OF SPEECH ms: min', ae[0], 'p50', q(0.5), 'p90', q(0.9), 'max', ae[ae.length - 1]);
const fin = lat.map((l) => l.finalAt - l.speechMs).filter((x) => Number.isFinite(x)).sort((a, b) => a - b);
console.log('final transcript after end of speech ms: p50', fin[Math.floor(fin.length / 2)], 'max', fin[fin.length - 1]);
const setup = r.map((x) => x.setupMs).filter(Boolean).sort((a, b) => a - b);
console.log('ws setup ms p50', setup[Math.floor(setup.length / 2)], 'max', setup[setup.length - 1]);
const qc = r.filter((x) => x.kind === 'pos' && x.id.includes('-q') && !x.error);
const qHit = qc.map((c) => ({ id: c.id, t: c.events.find((e) => e.text.toLowerCase().includes(c.expect))?.t })).filter((x) => x.t != null);
console.log('"Hey <name>, <request>" clips: first interim containing name ms (since start of audio) p50', qHit.map((x) => x.t).sort((a, b) => a - b)[Math.floor(qHit.length / 2)], 'n', qHit.length, '/', qc.length);
console.log('NEGATIVES finals:');
for (const c of r.filter((x) => x.kind === 'neg')) console.log(' ', c.id.padEnd(28), JSON.stringify(c.finalText));
console.log('misses (no expected name in final):', r.filter((x) => x.kind === 'pos' && !x.error && !x.finalText.toLowerCase().includes(x.expect)).map((x) => `${x.id}: ${x.finalText}`));
