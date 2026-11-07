// Does a constrained ephemeral token (as minted by src/main/live-auth.ts) honour client-sent languageCodes/customVocabulary?
import { readFileSync } from 'node:fs';
import { GoogleGenAI, Modality } from '@google/genai';
import dotenv from 'dotenv';
dotenv.config({ path: new URL('../../.env', import.meta.url).pathname, quiet: true });
const MODEL = 'gemini-3.5-transcribe-live';
const root = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY, httpOptions: { apiVersion: 'v1alpha' } });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function pcm(id) { const b = readFileSync(new URL(`./audio/${id}.wav`, import.meta.url)); return b.subarray(b.indexOf(Buffer.from('data')) + 8); }
async function mint(constraintCfg) {
  const now = Date.now();
  const t = await root.authTokens.create({ config: { uses: 1, expireTime: new Date(now + 600000).toISOString(), newSessionExpireTime: new Date(now + 60000).toISOString(), liveConnectConstraints: { model: MODEL, config: constraintCfg }, httpOptions: { apiVersion: 'v1alpha' } } });
  return t.name;
}
async function run(id, constraintCfg, clientCfg) {
  const tok = await mint(constraintCfg);
  const ai = new GoogleGenAI({ apiKey: tok, httpOptions: { apiVersion: process.env.CLIENT_VER || 'v1alpha' } });
  const texts = [];
  const s = await ai.live.connect({ model: MODEL, config: { responseModalities: [Modality.TEXT], inputAudioTranscription: clientCfg }, callbacks: { onmessage: (m) => { const sc = m.serverContent; if (sc?.interimInputTranscription?.text) texts.push('i:' + sc.interimInputTranscription.text); if (sc?.inputTranscription?.text) texts.push('F:' + sc.inputTranscription.text); }, onerror: (e) => texts.push('ERR ' + (e?.message ?? e)), onclose: (e) => texts.push('CLOSE ' + (e?.reason ?? '')) } });
  const send = (b) => s.sendRealtimeInput({ audio: { data: b.toString('base64'), mimeType: 'audio/pcm;rate=16000' } });
  const noise = () => { const b = Buffer.alloc(3200); for (let i = 0; i < 1600; i++) b.writeInt16LE(Math.round((Math.random() - 0.5) * 60), i * 2); return b; };
  for (let i = 0; i < 10; i++) { send(noise()); await sleep(100); }
  const p = pcm(id);
  for (let i = 0; i < p.length; i += 3200) { send(p.subarray(i, i + 3200)); await sleep(100); }
  for (let i = 0; i < 50; i++) { send(noise()); await sleep(100); }
  s.close();
  return texts;
}
const vocab = { languageCodes: ['en-GB', 'en-US'], customVocabulary: ['marcus', 'amelia'] };
const variants = { 'locked {} + client hints': [{ inputAudioTranscription: {} }, vocab], 'only modality locked + client hints': [{}, vocab], 'locked {} + no hints': [{ inputAudioTranscription: {} }, {}] };
const clips = process.argv.slice(2).length ? process.argv.slice(2) : ['amelia.flous'];
for (const [name, [constraint, client]] of Object.entries(variants).slice(0, 1)) {
  const results = [];
  for (let n = 0; n < 3; n++) for (const c of clips) { try { results.push(`${c}: ${JSON.stringify((await run(c, { responseModalities: [Modality.TEXT], ...constraint }, client)).slice(-3))}`); } catch (e) { results.push(`${c}: THROW ${e.message}`); } }
  console.log(`== ${name}\n  ` + results.join('\n  '));
}
