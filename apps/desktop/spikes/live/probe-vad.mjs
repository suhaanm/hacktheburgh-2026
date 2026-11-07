// VAD sensitivity vs latency: end of streamed speech -> first model audio, for a few configs (fake mic, TTS speech).
import { fakeMic, fakeSpeaker, loadLive, mintAuth, log, sleep, speech, TEST_SYSTEM_INSTRUCTION, waitFor } from './harness.mjs'
const live = await loadLive()
const CONFIGS = {
  'default (server)': undefined,
  'start LOW': { startOfSpeechSensitivity: 'START_SENSITIVITY_LOW' },
  'start LOW + end LOW': { startOfSpeechSensitivity: 'START_SENSITIVITY_LOW', endOfSpeechSensitivity: 'END_SENSITIVITY_LOW' },
}
for (const [name, vad] of Object.entries(CONFIGS)) {
  const mic = fakeMic(), speaker = fakeSpeaker()
  const session = new live.LiveSession({
    host: { getAuth: () => mintAuth('token'), systemInstruction: async () => TEST_SYSTEM_INSTRUCTION },
    audioIn: mic, audioOut: speaker, model: 'gemini-3.8-live', idleTimeoutMs: 0, vad,
    toolHandler: async () => ({ found: true, confidence: 0.9 }),
  })
  const heard = []
  session.on('transcript', (t) => t.final && t.role === 'user' && heard.push(t.text))
  await session.start({ voiceName: 'Charon' })
  await sleep(1000)
  const lat = []
  for (const [n, text] of [['q1', 'Hey, can you show me where the start call button is?'], ['q4', 'Tell me everything I should know about the keyboard, slowly, one key group at a time.']]) {
    await mic.say(speech(n, text), { leadMs: 200 })
    const endAt = Date.now()
    const ok = await waitFor(session, 'state', (s) => s.phase === 'speaking', 15_000).then(() => true, () => false)
    lat.push(ok ? Date.now() - endAt : null)
    await waitFor(session, 'state', (s) => s.phase === 'live', 30_000).catch(() => undefined)
    await sleep(800)
  }
  log(name.padEnd(22), 'end-of-speech -> first audio ms:', JSON.stringify(lat), '| heard', heard.length, 'of 2')
  await session.stop('stop')
}
process.exit(0)
