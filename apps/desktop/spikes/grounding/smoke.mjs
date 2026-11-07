// One real call per shape; prints structure so we adapt to the actual API (never the key).
import fs from 'node:fs';
import { makeClient, timed, outputText, functionCalls, usageOf, BOX_SCHEMA } from './lib.mjs';

const client = makeClient();
const imgPath = process.argv[2];
const hasImg = imgPath && imgPath !== '-';
const b64 = hasImg ? fs.readFileSync(imgPath).toString('base64') : null;
const mime = imgPath?.endsWith('.png') ? 'image/png' : 'image/jpeg';

const which = process.argv[3] ?? 'text';

if (which === 'text') {
  const r = await timed(client, { model: 'gemini-3.8-flash', input: 'Reply with the single word: pong', store: false, generation_config: { thinking_level: 'low' } });
  console.log(r.ok ? { ms: r.ms, text: outputText(r.interaction), usage: usageOf(r.interaction), stepTypes: r.interaction.steps.map((s) => s.type) } : r);
}

if (which === 'box') {
  const model = process.argv[4] ?? 'gemini-3.8-flash';
  const r = await timed(
    client,
    {
      model,
      store: false,
      input: [
        { type: 'text', text: 'Locate: ' + (process.argv[5] ?? 'the main heading') + '. Return its bounding box.' },
        { type: 'image', data: b64, mime_type: mime, resolution: 'high' },
      ],
      generation_config: { thinking_level: 'low' },
      response_format: { type: 'text', mime_type: 'application/json', schema: BOX_SCHEMA },
    },
    { timeoutMs: 120000 },
  );
  console.log(r.ok ? { ms: r.ms, text: outputText(r.interaction), usage: usageOf(r.interaction), stepTypes: r.interaction.steps.map((s) => s.type) } : r);
}

if (which === 'cu') {
  const model = process.argv[4] ?? 'gemini-3.8-flash';
  const r = await timed(
    client,
    {
      model,
      store: false,
      input: [
        { type: 'text', text: 'Task: click ' + (process.argv[5] ?? 'the main heading') + '.' },
        { type: 'image', data: b64, mime_type: mime, resolution: 'ultra_high' },
      ],
      generation_config: { thinking_level: 'low' },
      tools: [{ type: 'computer_use', environment: 'browser' }],
    },
    { timeoutMs: 120000 },
  );
  if (!r.ok) console.log(r);
  else console.log({ ms: r.ms, calls: JSON.stringify(functionCalls(r.interaction)), text: outputText(r.interaction), usage: usageOf(r.interaction), stepTypes: r.interaction.steps.map((s) => s.type) });
}
