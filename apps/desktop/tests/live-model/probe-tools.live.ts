// PROBE (manual, a few tenths of a cent): does the real Live model call our four tools, and under what prompting? Prints event TYPES and
// tool NAMES only. Text turns isolate tool-calling from speech recognition; one audio turn follows.
import { describe, it } from 'vitest'
import { LiveConnection } from '../../src/main/live/connection'
import { buildSetup, msg, type LiveServerEvent } from '../../src/main/live/wire'
import { buildToolDeclarations } from '../../src/main/live/tools'
import { LIVE_SYSTEM_INSTRUCTION } from '../../src/main/live/prompt'
import { createTokenMinter } from '../../src/main/live/token'
import { liveModelId } from '../../src/main/live/flags'

const cands = { items: [{ id: 'read_case', label: 'Read the household record' }, { id: 'calc_a', label: 'Run calculator A' }, { id: 'cliff_a', label: 'Check cliff edges (A)' }] }

async function run(label: string, o: { system: string; prompts: string[]; behavior?: 'drop' | 'keep'; thinking?: boolean; tools?: any[]; lock?: 'model' | 'none' | 'setup' }): Promise<void> {
  const model = liveModelId(process.env)!
  const tools = o.tools ?? buildToolDeclarations(cands)
  if (o.behavior === 'drop') for (const t of tools) delete (t as { behavior?: string }).behavior
  const seen: string[] = []
  const calls: string[] = []
  let audioChunks = 0
  const conn = new LiveConnection({
    getToken: async () => (await createTokenMinter({ env: process.env, lock: o.lock }).mint(model)).token,
    buildSetup: (h) => buildSetup({ model, voiceName: 'Sulafat', systemInstruction: o.system, tools, resumptionHandle: h }),
    onEvent: (e: LiveServerEvent) => {
      if (e.type === 'audio') audioChunks++
      else if (e.type === 'toolCall') for (const c of e.calls) calls.push(`${c.name}(${Object.keys(c.args).join(',')})`)
      seen.push(e.type)
      if (e.type === 'toolCall') for (const c of e.calls) conn.send(msg.toolResponse([{ id: c.id, name: c.name, response: { ok: true, found: true }, scheduling: 'SILENT' }]))
    },
    onClosed: (i) => seen.push(`closed:${i.code}`),
  })
  await conn.connect()
  for (const p of o.prompts) {
    conn.send(msg.text(p))
    await new Promise((r) => setTimeout(r, 6000))
  }
  conn.close()
  const counts = seen.reduce<Record<string, number>>((m, t) => ((m[t] = (m[t] ?? 0) + 1), m), {})
  process.stdout.write(`PROBE ${label}: tool_calls=${JSON.stringify(calls)} audio_chunks=${audioChunks} events=${JSON.stringify(counts)}\n`)
}

const OLD_POINT = {
  name: 'point_at',
  behavior: 'NON_BLOCKING' as const,
  description: "Draws an arrow and ring on the learner's real screen at one on-screen element. Call it the moment you tell the learner to look at, click or find something visible, in the same breath as speaking. Returns found=false when the element cannot be located: then say you cannot see it and ask the learner to describe or scroll; never guess. Arrows are guidance only and never click anything.",
  parameters: { type: 'object', properties: { target: { type: 'string', description: 'Purely visual description of the element, e.g. "the green Start call button at the bottom of the video window".' } }, required: ['target'] },
}
const MINE_NO_MAXLEN = buildToolDeclarations(cands).map((t) => JSON.parse(JSON.stringify(t, (k, v) => (k === 'maxLength' ? undefined : v))))
const TEACH = 'You are a patient guide that teaches people to use their computer. Speak in short plain sentences. When you tell the learner to look at or click something on screen, ALWAYS call point_at in the same breath.'

describe('probe', () => {
  it('does the token lock hide the tools?', async () => {
    const prompts = ['Please point at the submit button on the screen.', 'Where is the save button? Show me.']
    await run('lock=setup (as before: model in bidiGenerateContentSetup, no mask)', { system: TEACH, prompts, tools: [OLD_POINT], lock: 'setup' })
    await run('lock=none (no constraint at all)', { system: TEACH, prompts, tools: [OLD_POINT], lock: 'none' })
    await run('lock=model (field mask: model)', { system: TEACH, prompts, tools: [OLD_POINT], lock: 'model' })
  }, 180_000)
})
