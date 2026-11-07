// Raw protocol probe: connects with the real LiveConnection, sends one text turn, prints the event shapes.
// usage: node probe.mjs [token|key] [voice] [--thinking] [--clientContent]
import { loadLive, mintAuth, TEST_SYSTEM_INSTRUCTION, log, sleep } from './harness.mjs'

const mode = process.argv[2] === 'key' ? 'key' : 'token'
const voice = process.argv[3] && !process.argv[3].startsWith('--') ? process.argv[3] : 'Charon'
const thinking = process.argv.includes('--thinking')
const live = await loadLive()
const auth = await mintAuth(mode)
log('auth mode', auth.kind, 'token-shape', auth.kind === 'token' ? auth.value.slice(0, 12) + '...' : '(key)')

const counts = {}
const first = {}
let tText = 0
const conn = new live.LiveConnection({
  getAuth: async () => auth,
  buildSetup: (h) =>
    live.buildSetup({
      model: 'gemini-3.8-live',
      voiceName: voice,
      systemInstruction: TEST_SYSTEM_INSTRUCTION,
      tools: live.LIVE_TOOLS,
      resumptionHandle: h,
      thinkingLevel: thinking ? 'MINIMAL' : undefined,
    }),
  onEvent: (e) => {
    counts[e.type] = (counts[e.type] ?? 0) + 1
    if (!first[e.type]) {
      first[e.type] = Date.now()
      const shown = e.type === 'audio' ? { ...e, base64: `<${e.base64.length} b64 chars>` } : e
      log('first', e.type, JSON.stringify(shown).slice(0, 220), tText ? `(+${Date.now() - tText}ms from text)` : '')
    }
    if (e.type === 'outputTranscription' || e.type === 'inputTranscription') log(' ', e.type, JSON.stringify(e.text))
  },
  onClosed: (i) => log('closed', i),
  onReconnecting: (w) => log('reconnecting', w),
  onReconnected: (i) => log('reconnected', i),
  log: (...a) => log('[conn]', ...a),
})
const ts = Date.now()
try {
  await conn.connect()
} catch (err) {
  log('CONNECT FAILED:', err.message)
  process.exit(1)
}
log('setupComplete in', Date.now() - ts, 'ms')
tText = Date.now()
if (process.argv.includes('--clientContent')) conn.send(live.msg.clientContent('Say hello to the learner in five words.', true))
else conn.send(live.msg.text('Say hello to the learner in five words.'))
await sleep(7000)
log('counts', JSON.stringify(counts))
log('resumption handle present:', !!conn.resumptionHandle)
conn.close()
await sleep(300)
process.exit(0)
