// Docs conflict: is a function declaration WITHOUT `behavior` blocking or non-blocking on gemini-3.8-live?
// Method: leave the tool call unanswered, ask an unrelated question, see whether the model answers it while the call is pending.
import { loadLive, mintAuth, log, sleep } from './harness.mjs'
const live = await loadLive()
const SI = 'You are a helpful voice assistant. When the user asks about the weather, call get_weather. Answer any other question briefly.'
async function variant(behavior) {
  const tool = { name: 'get_weather', description: 'Gets the current weather. Call it whenever the user asks about the weather.', parameters: { type: 'object', properties: { city: { type: 'string' } } } }
  if (behavior) tool.behavior = behavior
  let callId, audioAfterQ = 0, qAt = 0, text = ''
  const conn = new live.LiveConnection({
    getAuth: () => mintAuth('token'),
    buildSetup: (h) => live.buildSetup({ model: 'gemini-3.8-live', voiceName: 'Charon', systemInstruction: SI, tools: [tool], resumptionHandle: h }),
    onEvent: (e) => {
      if (e.type === 'toolCall') callId = e.calls[0].id
      if (e.type === 'audio' && qAt) audioAfterQ += e.base64.length
      if (e.type === 'outputTranscription' && qAt) text += e.text
    },
    onClosed: () => {},
  })
  await conn.connect()
  conn.send(live.msg.text("What's the weather like in London right now?"))
  const t = Date.now()
  while (!callId && Date.now() - t < 15000) await sleep(100)
  await sleep(3000)
  qAt = Date.now()
  conn.send(live.msg.text('Unrelated quick question while you wait: what is two plus two? Answer in three words.'))
  await sleep(6000)
  log(String(behavior ?? '(omitted)').padEnd(14), 'answers the unrelated question while the call is pending:', audioAfterQ > 4000 ? 'YES (non-blocking)' : 'NO (blocked)', JSON.stringify(text.trim()).slice(0, 60))
  conn.close()
}
for (const b of [undefined, 'NON_BLOCKING', 'BLOCKING']) await variant(b)
process.exit(0)
