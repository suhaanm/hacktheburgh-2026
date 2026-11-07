// A/B: does language hint / custom vocabulary fix the mis-hearings? Runs the clips whose baseline transcript lacked the exact name.
import { readFileSync, writeFileSync } from 'node:fs';
import { transcribeClip } from './transcribe.mjs';

const base = JSON.parse(readFileSync(new URL('./results/harvest.json', import.meta.url)));
const lastText = (c) => c.finalText || [...c.events].reverse().find((e) => e.kind === 'interim')?.text || '';
const bad = base.filter((c) => c.kind === 'pos' && !c.id.includes('-q') && !lastText(c).toLowerCase().includes(c.expect));
const good = base.filter((c) => c.kind === 'pos' && !c.id.includes('-q') && lastText(c).toLowerCase().includes(c.expect)).slice(0, 6);
const set = [...bad, ...good];
const configs = {
  baseline: {},
  lang: { languageCodes: ['en-GB'] },
  vocab: { vocab: ['Marcus', 'Amelia'] },
  both: { languageCodes: ['en-GB'], vocab: ['Marcus', 'Amelia'] },
};
const out = {};
for (const [name, cfg] of Object.entries(configs)) {
  let i = 0;
  const rows = [];
  await Promise.all(Array.from({ length: 5 }, async () => {
    while (i < set.length) {
      const c = set[i++];
      const r = await transcribeClip(new URL(`./${c.wav}`, import.meta.url).pathname, { pace: 1, tailMs: 3500, timeoutMs: 2000, ...cfg });
      const t = r.finalText || [...r.events].reverse().find((e) => e.kind === 'interim')?.text || '';
      rows.push({ id: c.id, expect: c.expect, text: t });
    }
  }));
  out[name] = rows.sort((a, b) => a.id.localeCompare(b.id));
  const hits = rows.filter((r) => r.text.toLowerCase().includes(r.expect)).length;
  console.log(name.padEnd(9), `name heard exactly: ${hits}/${rows.length}`);
}
writeFileSync(new URL('./results/ab.json', import.meta.url), JSON.stringify(out, null, 1));
for (const r of out.baseline) console.log(r.id.padEnd(18), '|', r.text.padEnd(22), '|', (out.lang.find((x) => x.id === r.id)?.text ?? '').padEnd(22), '|', (out.vocab.find((x) => x.id === r.id)?.text ?? '').padEnd(22), '|', out.both.find((x) => x.id === r.id)?.text);
