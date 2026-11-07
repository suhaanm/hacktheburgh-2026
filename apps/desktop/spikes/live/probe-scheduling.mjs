// Settles the docs conflicts about NON_BLOCKING tool responses: where `scheduling` lives (top level vs inside `response`)
// and whether INTERRUPT / INTERRUPTED is the valid value. Observation: does the model speak the tool result after we answer?
import { loadLive, mintAuth, log, sleep } from './harness.mjs'
const live = await loadLive()
const TOOL = { name: 'get_weather', behavior: 'NON_BLOCKING', description: 'Gets the current weather. Call it whenever the user asks about the weather.', parameters: { type: 'object', properties: { city: { type: 'string' } } } }
const SI = 'You are a helpful voice assistant. When the user asks about the weather, call get_weather. When a tool result arrives, tell the user what it says in one short sentence.'

async function variant(label, build) {
  let callId, spokeAfter = 0, textAfter = '', respondedAt = 0, closed = '', total = 0
  const conn = new live.LiveConnection({
    getAuth: () => mintAuth('token'),
    buildSetup: (h) => live.buildSetup({ model: 'gemini-3.8-live', voiceName: 'Charon', systemInstruction: SI, tools: [TOOL], resumptionHandle: h }),
    onEvent: (e) => {
      if (e.type === 'toolCall') callId = e.calls[0].id
      if (e.type === 'audio') { total += e.base64.length; if (respondedAt) spokeAfter += e.base64.length }
      if (e.type === 'outputTranscription' && respondedAt) textAfter += e.text
    },
    onClosed: (i) => { closed = `${i.code} ${i.reason}` },
  })
  await conn.connect()
  conn.send(live.msg.text("What's the weather like in London right now?"))
  const t = Date.now()
  while (!callId && Date.now() - t < 15000) await sleep(100)
  if (!callId) { log(label, 'NO TOOL CALL'); conn.close(); return }
  await sleep(2500) // let any "let me check" filler finish so only the reaction to the result is measured
  respondedAt = Date.now()
  conn.send({ toolResponse: { functionResponses: [build(callId)] } })
  await sleep(7000)
  log(label.padEnd(34), `speech after result: ${spokeAfter > 4000 ? 'YES' : 'no '} (${Math.round(spokeAfter * 0.75)} bytes)`, JSON.stringify(textAfter.trim()).slice(0, 90), closed ? `| closed ${closed}` : '')
  conn.close()
}
const R = 'It is sunny and 21 degrees. Tell the user.'
await variant('top-level SILENT', (id) => ({ id, name: 'get_weather', response: { result: R }, scheduling: 'SILENT' }))
await variant('top-level INTERRUPT', (id) => ({ id, name: 'get_weather', response: { result: R }, scheduling: 'INTERRUPT' }))
await variant('top-level WHEN_IDLE', (id) => ({ id, name: 'get_weather', response: { result: R }, scheduling: 'WHEN_IDLE' }))
await variant('inside response: SILENT (docs example)', (id) => ({ id, name: 'get_weather', response: { result: R, scheduling: 'SILENT' } }))
await variant('top-level INTERRUPTED (migration.md)', (id) => ({ id, name: 'get_weather', response: { result: R }, scheduling: 'INTERRUPTED' }))
process.exit(0)
