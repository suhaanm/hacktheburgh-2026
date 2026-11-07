// Runs every clip in audio/manifest.json through transcribe-live; writes results/harvest.json (alias + latency raw data).
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { transcribeClip } from './transcribe.mjs';

const here = dirname(fileURLToPath(import.meta.url));
mkdirSync(join(here, 'results'), { recursive: true });
const args = Object.fromEntries(process.argv.slice(2).map((a) => a.replace(/^--/, '').split('=')));
const conc = Number(args.conc ?? 6);
const pace = Number(args.pace ?? 1);
const only = args.only; // substring filter
const outName = args.out ?? 'harvest.json';
const vocab = args.vocab ? args.vocab.split(',') : undefined;
const manifest = JSON.parse(readFileSync(join(here, 'audio', 'manifest.json'), 'utf8')).filter((c) => !only || c.id.includes(only));

const results = [];
let idx = 0;
async function worker() {
  while (idx < manifest.length) {
    const clip = manifest[idx++];
    try {
      const r = await transcribeClip(join(here, clip.wav), { pace, vocab });
      const firstInterim = r.events.find((e) => e.kind === 'interim');
      results.push({ ...clip, speechMs: Math.round(r.speechMs), setupMs: Math.round(r.setupMs), finalText: r.finalText, firstInterimAt: firstInterim ? Math.round(firstInterim.t) : null, events: r.events.map((e) => ({ ...e, t: Math.round(e.t) })) });
      process.stderr.write(`${clip.id}: ${r.finalText}\n`);
    } catch (e) {
      results.push({ ...clip, error: String(e?.message ?? e) });
      process.stderr.write(`${clip.id}: ERROR ${e?.message ?? e}\n`);
    }
  }
}
await Promise.all(Array.from({ length: conc }, worker));
writeFileSync(join(here, 'results', outName), JSON.stringify(results, null, 1));
console.log(`${results.length} clips -> results/${outName}; errors: ${results.filter((r) => r.error).length}`);
