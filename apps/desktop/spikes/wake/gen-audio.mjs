// Generates synthetic 16 kHz mono PCM16 WAVs via macOS `say` + `afconvert`, plus audio/manifest.json.
import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, 'audio');
mkdirSync(out, { recursive: true });

const VOICES = [
  ['daniel', 'Daniel', 'en_GB'], ['samantha', 'Samantha', 'en_US'], ['karen', 'Karen', 'en_AU'],
  ['moira', 'Moira', 'en_IE'], ['rishi', 'Rishi', 'en_IN'], ['tara', 'Tara', 'en_IN'],
  ['tessa', 'Tessa', 'en_ZA'], ['aman', 'Aman', 'en_IN'], ['fred', 'Fred', 'en_US'],
  ['kathy', 'Kathy', 'en_US'], ['ralph', 'Ralph', 'en_US'], ['eddyuk', 'Eddy (English (UK))', 'en_GB'],
  ['flous', 'Flo (English (US))', 'en_US'], ['reedus', 'Reed (English (US))', 'en_US'],
  ['sandyuk', 'Sandy (English (UK))', 'en_GB'], ['shelleyus', 'Shelley (English (US))', 'en_US'],
  ['grandmaus', 'Grandma (English (US))', 'en_US'], ['grandpauk', 'Grandpa (English (UK))', 'en_GB'],
];
const POS = [
  ['marcus', 'Hey Marcus', 'marcus'],
  ['amelia', 'Hey Amelia', 'amelia'],
  ['marcus-q', 'Hey Marcus, make the text bigger', 'marcus'],
  ['amelia-q', 'Hey Amelia, how do I join the video call', 'amelia'],
];
const NEG_VOICES = ['daniel', 'samantha', 'rishi'];
const NEG = [
  ['neg-google', 'Hey Google, what is the weather today'],
  ['neg-alexa', 'Hey Alexa, set a timer for ten minutes'],
  ['neg-aurelius', 'Marcus Aurelius was a Roman emperor and philosopher'],
  ['neg-amelia-past', 'I spoke to my friend Amelia yesterday about the garden'],
  ['neg-mark', 'Hey Mark, are you coming to dinner tonight'],
  ['neg-america', 'Hey America, welcome to the show'],
  ['neg-emily', 'Hey Emily, did you see the news'],
  ['neg-market', 'I went to the market to buy some apples'],
  ['neg-help', 'Hey there, I need some help with my computer'],
  ['neg-chat', 'We should video call grandma on Sunday and make the text bigger'],
  ['neg-musicus', 'Hey Marcia, can you pass the salt'],
  ['neg-camelia', 'The camellia bush in the garden is beautiful this year'],
];

const manifest = [];
const gen = (id, voiceKey, voiceName, accent, text, kind, expect) => {
  const aiff = join(out, `${id}.aiff`);
  const wav = join(out, `${id}.wav`);
  execFileSync('say', ['-v', voiceName, '-o', aiff, text]);
  execFileSync('afconvert', ['-f', 'WAVE', '-d', 'LEI16@16000', '-c', '1', aiff, wav]);
  rmSync(aiff);
  manifest.push({ id, voice: voiceKey, accent, text, kind, expect, wav: `audio/${id}.wav` });
};
for (const [vk, vn, acc] of VOICES) for (const [pid, text, expect] of POS) gen(`${pid}.${vk}`, vk, vn, acc, text, 'pos', expect);
for (const vk of NEG_VOICES) {
  const [, vn, acc] = VOICES.find((v) => v[0] === vk);
  for (const [nid, text] of NEG) gen(`${nid}.${vk}`, vk, vn, acc, text, 'neg', null);
}
writeFileSync(join(out, 'manifest.json'), JSON.stringify(manifest, null, 1));
console.log(`wrote ${manifest.length} clips`);
