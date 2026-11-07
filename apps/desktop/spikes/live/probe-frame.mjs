// Does the Live server drop the session for the mock capture's TINY_JPEG (the only frame in a mock-capture run)?
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { loadLive, mintAuth, log, sleep, REPO, TEST_SYSTEM_INSTRUCTION } from './harness.mjs'
const src = readFileSync(path.join(REPO, 'src/main/mocks.ts'), 'utf8')
const m = src.match(/TINY_JPEG\s*=\s*\n?\s*['"`]([A-Za-z0-9+/=]+)['"`]/)
if (!m) { console.log('could not extract TINY_JPEG'); process.exit(2) }
const tiny = m[1]
log('TINY_JPEG base64 chars', tiny.length)
const live = await loadLive()
let closed = null
const conn = new live.LiveConnection({
  getAuth: () => mintAuth('token'),
  buildSetup: (h) => live.buildSetup({ model: 'gemini-3.8-live', voiceName: 'Charon', systemInstruction: TEST_SYSTEM_INSTRUCTION, tools: live.LIVE_TOOLS, resumptionHandle: h }),
  onEvent: () => {},
  onClosed: (i) => { closed = i },
  onReconnecting: (w) => log('reconnecting', w),
  maxReconnectAttempts: 1,
  log: (...a) => log('[conn]', ...a),
})
await conn.connect()
log('connected; sending TINY_JPEG once per second for 6 s')
for (let i = 0; i < 6; i++) { conn.send(live.msg.video(tiny)); await sleep(1000) }
log('state', conn.state, 'closed', JSON.stringify(closed))
conn.close()
process.exit(0)
