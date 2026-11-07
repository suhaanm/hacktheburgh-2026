// Builds a "microphone" WAV for Chromium's --use-file-for-fake-audio-capture: 1 s room tone, the clip, 5 s room tone.
import { readFileSync, writeFileSync } from 'node:fs';
const id = process.argv[2] ?? 'marcus.daniel';
const out = process.argv[3] ?? '/tmp/wake-fake-mic.wav';
const b = readFileSync(new URL(`../audio/${id}.wav`, import.meta.url));
const pcm = b.subarray(b.indexOf(Buffer.from('data')) + 8);
const tone = (s) => { const t = Buffer.alloc(s * 16000 * 2); for (let i = 0; i < s * 16000; i++) t.writeInt16LE(Math.round((Math.random() - 0.5) * 60), i * 2); return t; };
const data = Buffer.concat([tone(1), pcm, tone(5)]);
const h = Buffer.alloc(44);
h.write('RIFF', 0); h.writeUInt32LE(36 + data.length, 4); h.write('WAVEfmt ', 8); h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22);
h.writeUInt32LE(16000, 24); h.writeUInt32LE(32000, 28); h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34); h.write('data', 36); h.writeUInt32LE(data.length, 40);
writeFileSync(out, Buffer.concat([h, data]));
console.log(`wrote ${out} (${((data.length / 32000)).toFixed(1)} s)`);
