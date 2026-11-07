import { transcribeClip } from './transcribe.mjs';
const clips = ['amelia.flous', 'marcus.fred', 'amelia.rishi', 'marcus.aman', 'amelia.eddyuk'];
const cfgs = { 'en-GB': ['en-GB'], 'en-US': ['en-US'], 'GB+US': ['en-GB', 'en-US'], 'GB+US+IN': ['en-GB', 'en-US', 'en-IN'] };
for (const [name, languageCodes] of Object.entries(cfgs)) {
  const res = await Promise.all(clips.map(async (c) => {
    const r = await transcribeClip(new URL(`./audio/${c}.wav`, import.meta.url).pathname, { pace: 1, tailMs: 3500, timeoutMs: 1500, languageCodes, vocab: ['Marcus', 'Amelia'] });
    return `${c}: ${JSON.stringify(r.finalText || [...r.events].reverse().find((e) => e.kind === 'interim')?.text || '')}`;
  }));
  console.log(name.padEnd(9), res.join(' | '));
}
