// Streams a 16 kHz mono PCM16 WAV through gemini-3.5-transcribe-live and records every transcript event with timing.
import { readFileSync } from 'node:fs';
import { GoogleGenAI } from '@google/genai';
import dotenv from 'dotenv';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: join(here, '..', '..', '.env'), quiet: true });
if (!process.env.GEMINI_API_KEY) throw new Error('GEMINI_API_KEY missing in REPO/.env');

export const MODEL = process.env.MODEL_TRANSCRIBE || 'gemini-3.5-transcribe-live';
const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function readWavPcm(path) {
  const buf = readFileSync(path);
  const dataIdx = buf.indexOf(Buffer.from('data'));
  return buf.subarray(dataIdx + 8); // PCM16LE mono 16 kHz
}

/**
 * pace: 1 = real time, 4 = 4x faster (alias harvesting), 0 = as fast as possible.
 * Resolves after the final transcript (or timeout). events[].t is ms since first audio byte was sent.
 */
export async function transcribeClip(path, opts = {}) {
  const { pace = 1, tailMs = 4000, streamEnd = false, vocab, mode, languageCodes, timeoutMs = 20000, chunkMs = 100 } = opts;
  const pcm = readWavPcm(path);
  const speechMs = (pcm.length / 2 / 16000) * 1000;
  const events = [];
  let t0 = null, opened = 0, setupMs = 0;
  const tConnect = performance.now();
  let finalSeen = null;
  const inputAudioTranscription = {};
  if (vocab) inputAudioTranscription.customVocabulary = vocab;
  if (mode) inputAudioTranscription.mode = mode;
  if (languageCodes) inputAudioTranscription.languageCodes = languageCodes;
  const session = await ai.live.connect({
    model: MODEL,
    config: { responseModalities: ['TEXT'], inputAudioTranscription },
    callbacks: {
      onopen: () => { opened = performance.now(); setupMs = opened - tConnect; },
      onmessage: (msg) => {
        const sc = msg.serverContent;
        if (!sc) return;
        const t = t0 === null ? -1 : performance.now() - t0;
        if (sc.interimInputTranscription?.text !== undefined) events.push({ t, kind: 'interim', text: sc.interimInputTranscription.text });
        if (sc.inputTranscription?.text !== undefined) { events.push({ t, kind: 'final', text: sc.inputTranscription.text }); finalSeen = t; }
        if (opts.debug) console.error(JSON.stringify(msg));
      },
      onerror: (e) => events.push({ t: -2, kind: 'error', text: String(e?.message ?? e) }),
      onclose: () => {},
    },
  });
  const chunkBytes = (16000 * 2 * chunkMs) / 1000;
  const silence = Buffer.alloc(chunkBytes);
  const send = (b) => session.sendRealtimeInput({ audio: { data: b.toString('base64'), mimeType: 'audio/pcm;rate=16000' } });
  t0 = performance.now();
  const interval = pace > 0 ? chunkMs / pace : 0;
  let next = t0;
  for (let i = 0; i < pcm.length; i += chunkBytes) {
    send(pcm.subarray(i, Math.min(i + chunkBytes, pcm.length)));
    next += interval;
    const wait = next - performance.now();
    if (wait > 0) await sleep(wait);
  }
  const speechEndSentAt = performance.now() - t0;
  if (streamEnd) session.sendRealtimeInput({ audioStreamEnd: true });
  const tailEnd = performance.now() + tailMs / Math.max(pace, 1);
  while (performance.now() < tailEnd && finalSeen === null) { send(silence); await sleep(interval || 10); }
  const deadline = performance.now() + timeoutMs;
  while (finalSeen === null && performance.now() < deadline) await sleep(50);
  // linger briefly to catch trailing finals
  await sleep(150);
  session.close();
  return { path, speechMs, speechEndSentAt, setupMs, events, finalText: events.filter((e) => e.kind === 'final').map((e) => e.text).join(' ').trim(), t0 };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const r = await transcribeClip(process.argv[2], { pace: 1, debug: process.argv.includes('--debug'), streamEnd: process.argv.includes('--stream-end') });
  console.log(JSON.stringify({ ...r, t0: undefined }, null, 1));
}
