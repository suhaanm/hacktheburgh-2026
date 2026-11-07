// Does audioStreamEnd (client-VAD "Hybrid VAD") speed up finals, and does the session keep working afterwards?
import { readFileSync } from 'node:fs';
import { GoogleGenAI, Modality } from '@google/genai';
import dotenv from 'dotenv';
dotenv.config({ path: new URL('../../.env', import.meta.url).pathname, quiet: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
const pcm = (id) => { const b = readFileSync(new URL(`./audio/${id}.wav`, import.meta.url)); return b.subarray(b.indexOf(Buffer.from('data')) + 8); };
const noise = () => { const b = Buffer.alloc(3200); for (let i = 0; i < 1600; i++) b.writeInt16LE(Math.round((Math.random() - 0.5) * 60), i * 2); return b; };
async function trial(useEnd) {
  const t0 = performance.now(); const log = [];
  const s = await ai.live.connect({ model: 'gemini-3.5-transcribe-live', config: { responseModalities: [Modality.TEXT], inputAudioTranscription: { languageCodes: ['en-GB', 'en-US'], customVocabulary: ['marcus', 'amelia'] } },
    callbacks: { onmessage: (m) => { const sc = m.serverContent; const t = Math.round(performance.now() - t0); if (sc?.interimInputTranscription?.text) log.push(`${t} i:${sc.interimInputTranscription.text}`); if (sc?.inputTranscription?.text) log.push(`${t} F:${sc.inputTranscription.text}`); if (m.voiceActivity) log.push(`${t} ${m.voiceActivity.type}`); }, onerror: (e) => log.push('ERR ' + e?.message), onclose: (e) => log.push(`${Math.round(performance.now() - t0)} CLOSE ${e?.reason ?? ''}`) } });
  const send = (b) => s.sendRealtimeInput({ audio: { data: b.toString('base64'), mimeType: 'audio/pcm;rate=16000' } });
  const play = async (id) => { const p = pcm(id); for (let i = 0; i < p.length; i += 3200) { send(p.subarray(i, i + 3200)); await sleep(100); } log.push(`${Math.round(performance.now() - t0)} --speech ${id} ended`); };
  const quiet = async (ms, end) => { for (let i = 0; i < ms / 100; i++) { send(noise()); await sleep(100); if (end && i === 5) { s.sendRealtimeInput({ audioStreamEnd: true }); log.push(`${Math.round(performance.now() - t0)} --audioStreamEnd sent`); } } };
  await quiet(1000);
  await play('amelia.flous'); await quiet(3500, useEnd);
  await play('marcus.daniel'); await quiet(3500, useEnd);
  s.close();
  return log;
}
for (const useEnd of [false, true]) console.log(`== audioStreamEnd ${useEnd}\n  ` + (await trial(useEnd)).join('\n  '));
