// Is a burst of pre-roll audio (100 ms chunks, all at once right after setup) what makes the server close with 1007?
import { loadLive, mintAuth, log, sleep, speech, TEST_SYSTEM_INSTRUCTION } from './harness.mjs'
const live = await loadLive()
const pcm = speech('q1', 'Hey, can you show me where the start call button is?')
async function run(label, chunkSamples, paceMs, tools) {
  let closed = null, audio = 0, user = ''
  const conn = new live.LiveConnection({
    getAuth: () => mintAuth('token'),
    buildSetup: (h) => live.buildSetup({ model: 'gemini-3.8-live', voiceName: 'Charon', systemInstruction: TEST_SYSTEM_INSTRUCTION, tools: tools ?? [], resumptionHandle: h }),
    onEvent: (e) => { if (e.type === 'audio') audio++; if (e.type === 'inputTranscription') user += e.text },
    onClosed: (i) => { closed = i }, onReconnecting: () => {}, maxReconnectAttempts: 0,
    log: (...a) => { if (a[0] === 'socket lost') closed = { code: a[1], reason: a[2] } },
  })
  await conn.connect()
  const i16 = new Int16Array(pcm.buffer, pcm.byteOffset, Math.floor(pcm.byteLength / 2))
  const chunks = live.pcm16ToBase64Chunks(i16, chunkSamples)
  for (const c of chunks) { conn.send(live.msg.audio(c)); if (paceMs) await sleep(paceMs) }
  await sleep(9000)
  log(label.padEnd(44), `chunks=${chunks.length}`, 'heard:', JSON.stringify(user.trim()).slice(0, 50), 'audio msgs:', audio, 'closed:', closed ? `${closed.code} ${closed.reason}` : 'no')
  conn.close()
}
await run('burst 100ms chunks, no tools', 1600, 0)
await run('burst 100ms chunks, all LIVE_TOOLS', 1600, 0, live.LIVE_TOOLS)
await run('real-time 32ms chunks, all LIVE_TOOLS', 512, 32, live.LIVE_TOOLS)
process.exit(0)
