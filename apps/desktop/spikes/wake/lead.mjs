import { readFileSync, writeFileSync } from 'node:fs';
import { transcribeClip, readWavPcm } from './transcribe.mjs';
// Prepend N ms of low-level noise ("room tone") to a clip and see if the empty-transcript voices recover.
const ids = ['amelia.eddyuk', 'amelia.grandmaus', 'amelia.reedus', 'marcus.sandyuk', 'amelia.sandyuk'];
function withLead(id, ms) {
  const buf = readFileSync(new URL(`./audio/${id}.wav`, import.meta.url));
  const di = buf.indexOf(Buffer.from('data'));
  const pcm = buf.subarray(di + 8);
  const n = Math.round((ms / 1000) * 16000);
  const lead = Buffer.alloc(n * 2);
  for (let i = 0; i < n; i++) lead.writeInt16LE(Math.round((Math.random() - 0.5) * 60), i * 2); // ~-60 dBFS hiss
  const out = Buffer.concat([buf.subarray(0, di + 8), lead, pcm]);
  const p = `/tmp/lead-${id}.wav`;
  writeFileSync(p, out);
  return p;
}
for (const id of ids) {
  const r = await transcribeClip(withLead(id, 1000), { pace: 1, tailMs: 3500, timeoutMs: 1500 });
  const t = r.finalText || [...r.events].reverse().find((e) => e.kind === 'interim')?.text || '';
  console.log(id.padEnd(18), JSON.stringify(t));
}
